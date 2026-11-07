#!/usr/bin/env python3
"""Patch Ferry's embedded web UI for queued multi-file uploads."""
from pathlib import Path
import re

root = Path("/src")
app_path = root / "internal/webui/assets/app.js"
html_path = root / "internal/webui/assets/index.html"
app = app_path.read_text(encoding="utf-8")
html = html_path.read_text(encoding="utf-8")

def once(source, old, new, label):
    n = source.count(old)
    if n != 1:
        raise SystemExit(f"Patch stopped: expected one match for {label}, found {n}")
    return source.replace(old, new, 1)

def block(source, pattern, replacement, label):
    result, n = re.subn(pattern, lambda _: replacement, source, count=1, flags=re.S)
    if n != 1:
        raise SystemExit(f"Patch stopped: expected one block for {label}, found {n}")
    return result

app = once(app,
    "let pastedAttachment = null;\nlet previewAttachment = null;",
    "let pastedAttachment = null;\nlet queuedFiles = [];\nlet uploading = false;\nlet previewAttachment = null;",
    "queue state")

app = block(app, r"function selectedAttachment\(\) \{.*?\n\}",
"""function selectedAttachments() {
  if (pastedAttachment) return [pastedAttachment];
  return queuedFiles;
}

function clearAttachment() {
  pastedAttachment = null;
  queuedFiles = [];
  photoInput.value = "";
  fileInput.value = "";
}""", "attachment selection")

app = block(app, r"function updateComposer\(\) \{.*?\n\}",
"""function updateComposer() {
  const selected = selectedAttachments();
  const first = selected[0] || null;
  if (first !== previewAttachment) {
    if (previewURL) URL.revokeObjectURL(previewURL);
    previewAttachment = first;
    previewURL = first?.type.startsWith("image/") ? URL.createObjectURL(first) : "";
    previewFailed = false;
  }
  const hasFiles = selected.length > 0;
  const isImage = Boolean(previewURL) && !previewFailed;
  fileChip.hidden = !hasFiles;
  composer.classList.toggle("has-attachment", hasFiles);
  fileChip.classList.toggle("is-image", isImage);
  fileChip.setAttribute("aria-label", hasFiles ? `${selected.length} selected attachment${selected.length === 1 ? "" : "s"}` : "");
  filePreview.hidden = !isImage;
  if (isImage) filePreview.src = previewURL;
  else filePreview.removeAttribute("src");
  fileName.textContent = selected.length > 1 ? `${selected.length} files selected` : (first?.name || "");
  textInput.disabled = hasFiles || uploading;
  sendButton.disabled = uploading || (!hasFiles && textInput.value.trim().length === 0);
}""", "composer preview")

app = block(app, r'composer\.addEventListener\("submit", async \(event\) => \{.*?\n\}\);',
"""composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const files = [...selectedAttachments()];
  const text = textInput.value;
  const generation = authGeneration;
  if (files.length === 0 && !text.trim()) return;

  uploading = files.length > 0;
  sendButton.disabled = true;
  sendError = "";
  activityStatus = files.length > 0 ? `Preparing ${files.length} files…` : "Sending…";
  renderStatus();
  updateComposer();

  try {
    if (files.length > 0) {
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        activityStatus = `Sending ${index + 1}/${files.length}: ${file.name}`;
        renderStatus();
        if (!await sendFile(file)) return;
        queuedFiles = queuedFiles.filter((queued) => queued !== file);
        if (pastedAttachment === file) pastedAttachment = null;
        updateComposer();
      }
      clearAttachment();
    } else {
      if (!await sendText(text)) return;
      textInput.value = "";
      resizeComposer();
    }
    activityStatus = "";
    await loadMessages();
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    renderStatus();
  } catch (error) {
    if (generation !== authGeneration || error.name === "AbortError") return;
    activityStatus = "";
    sendError = error.message;
    renderStatus();
  } finally {
    uploading = false;
    updateComposer();
  }
});""", "submit handler")

app = once(app,
    "  pastedAttachment = image;\n  photoInput.value = \"\";\n  fileInput.value = \"\";",
    "  pastedAttachment = image;\n  queuedFiles = [];\n  photoInput.value = \"\";\n  fileInput.value = \"\";",
    "pasted image reset")

app = block(app,
    r'photoInput\.addEventListener\("change", \(\) => \{.*?fileInput\.addEventListener\("change", \(\) => \{.*?\n\}\);',
"""photoInput.addEventListener("change", () => {
  if (photoInput.files.length > 0) {
    pastedAttachment = null;
    queuedFiles = Array.from(photoInput.files);
    fileInput.value = "";
  }
  updateComposer();
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) {
    pastedAttachment = null;
    queuedFiles = Array.from(fileInput.files);
    photoInput.value = "";
  }
  updateComposer();
});

// Desktop browsers can drop multiple files onto the composer.
composer.addEventListener("dragover", (event) => {
  if (event.dataTransfer?.types.includes("Files")) event.preventDefault();
});
composer.addEventListener("drop", (event) => {
  const files = Array.from(event.dataTransfer?.files || []);
  if (files.length === 0) return;
  event.preventDefault();
  pastedAttachment = null;
  queuedFiles = files;
  photoInput.value = "";
  fileInput.value = "";
  updateComposer();
});""", "file picker handlers")

app_path.write_text(app, encoding="utf-8")
html = once(html, '<input type="file" id="photo" accept="image/*,video/*" hidden>',
                 '<input type="file" id="photo" accept="image/*,video/*" multiple hidden>', "photo picker")
html = once(html, '<input type="file" id="file" hidden>',
                 '<input type="file" id="file" multiple hidden>', "file picker")
html_path.write_text(html, encoding="utf-8")
print("Ferry multi-file upload patch applied.")
