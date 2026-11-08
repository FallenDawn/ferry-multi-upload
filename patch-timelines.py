#!/usr/bin/env python3
"""Patch Ferry with persistent multi-timeline support."""
from pathlib import Path
import re

root = Path("/src")
store_path = root / "internal/ferry/store.go"
server_path = root / "internal/ferry/server.go"
app_path = root / "internal/webui/assets/app.js"
html_path = root / "internal/webui/assets/index.html"
css_path = root / "internal/webui/assets/app.css"

def once(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"Timeline patch stopped: expected one match for {label}, found {n}")
    return src.replace(old, new, 1)

store = store_path.read_text()
store = once(store, "if err := s.migrateSchemaColumns(ctx); err != nil {\n\t\treturn err\n\t}\n\treturn nil",
"""if err := s.migrateSchemaColumns(ctx); err != nil {
		return err
	}
	if err := s.ensureTimelineSchema(ctx); err != nil {
		return err
	}
	return nil""", "timeline schema migration")
store_path.write_text(store)

server = server_path.read_text()
server = once(server, 'api.HandleFunc("GET /api/v1/messages", s.listMessages)',
"""api.HandleFunc("GET /api/v1/messages", s.listMessages)
	api.HandleFunc("GET /api/v1/timelines", s.listTimelines)
	api.HandleFunc("POST /api/v1/timelines", s.createTimeline)
	api.HandleFunc("PATCH /api/v1/timelines/{timeline_id}", s.updateTimeline)
	api.HandleFunc("DELETE /api/v1/timelines/{timeline_id}", s.deleteTimeline)
	api.HandleFunc("PUT /api/v1/timelines/order", s.reorderTimelines)""", "timeline routes")
server = once(server,
"""messages, nextCursor, err := s.store.ListMessages(r.Context(), after, limit)
	if err != nil {""",
"""timelineID := r.URL.Query().Get("timeline_id")
	if timelineID == "" { timelineID = defaultTimelineID }
	exists, existsErr := s.store.TimelineExists(r.Context(), timelineID)
	if existsErr != nil { s.internalError(w, existsErr); return }
	if !exists { writeError(w, http.StatusNotFound, "not_found", "timeline not found"); return }
	messages, nextCursor, err := s.store.ListMessagesInTimeline(r.Context(), timelineID, after, limit)
	if err != nil {""", "timeline message filtering")
server = once(server,
"""message, err := s.store.CreateTextForDevice(r.Context(), currentDevice(r), string(request.Text))
	if errors.Is(err, ErrUnauthorized) {""",
"""message, err := s.store.CreateTextForDevice(r.Context(), currentDevice(r), string(request.Text))
	if err == nil {
		timelineID := r.Header.Get("X-Ferry-Timeline-ID")
		if timelineID == "" { timelineID = defaultTimelineID }
		err = s.store.AssignMessageTimeline(r.Context(), message.ID, timelineID)
	}
	if errors.Is(err, ErrUnauthorized) {""", "text timeline assignment")
server = once(server,
"""message, err := s.store.CreateFileForDevice(r.Context(), currentDevice(r), header.Filename, mediaType, source)
	if errors.Is(err, ErrUnauthorized) {""",
"""message, err := s.store.CreateFileForDevice(r.Context(), currentDevice(r), header.Filename, mediaType, source)
	if err == nil {
		timelineID := r.Header.Get("X-Ferry-Timeline-ID")
		if timelineID == "" { timelineID = defaultTimelineID }
		err = s.store.AssignMessageTimeline(r.Context(), message.ID, timelineID)
	}
	if errors.Is(err, ErrUnauthorized) {""", "file timeline assignment")
server_path.write_text(server)

html = html_path.read_text()
html = once(html, """          <button class="sidebar-item device-button" id="device-button" type="button" hidden>""",
"""          <div class="timeline-manager">
            <div class="timeline-manager-head"><span>YOUR TIMELINES</span><button id="new-timeline" type="button" aria-label="Create timeline" title="Create timeline">+</button></div>
            <div id="timeline-list" class="timeline-list" role="list"></div>
          </div>
          <button class="sidebar-item device-button" id="device-button" type="button" hidden>""", "timeline sidebar")
html_path.write_text(html)

css = css_path.read_text()
css += """
.timeline-manager { margin: 14px 0 8px; }
.timeline-manager-head { display:flex; align-items:center; justify-content:space-between; padding:0 9px 7px; color:var(--faint); font-size:10px; font-weight:700; letter-spacing:.08em; }
.timeline-manager-head button { width:25px; height:25px; border:0; border-radius:7px; background:transparent; color:inherit; font-size:20px; cursor:pointer; }
.timeline-manager-head button:hover { background:var(--soft); color:inherit; }
.timeline-list { display:grid; gap:3px; max-height:calc(100vh - 220px); overflow-y:auto; }
.timeline-row { display:flex; align-items:center; gap:3px; min-width:0; padding:2px 4px; border-radius:9px; }
.timeline-row.is-active,.timeline-row:hover { background:var(--soft); }
.timeline-row.dragging { opacity:.4; }
.timeline-select { min-width:0; flex:1; display:flex; align-items:center; gap:9px; padding:7px 6px; overflow:hidden; border:0; background:transparent; color:inherit; text-align:left; font-size:13px; cursor:pointer; }
.timeline-select span:last-child { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.timeline-dot { width:7px; height:7px; flex:0 0 auto; border:1.5px solid var(--muted); border-radius:50%; }
.timeline-row.is-active .timeline-dot { background:var(--contrast); border-color:var(--contrast); }
.timeline-menu { width:27px; height:27px; flex:0 0 auto; border:0; border-radius:7px; color:var(--muted); background:transparent; cursor:pointer; }
.timeline-menu:hover { background:var(--hover); color:inherit; }
@media(max-width:640px) {
 .timeline-manager-head span,.timeline-select span:last-child,.timeline-menu { display:none; }\n .timeline-manager-head button { display:grid; place-items:center; }
 .timeline-manager { margin-top:12px; }
 .timeline-row { justify-content:center; padding:3px 0; }
 .timeline-select { flex:0 0 auto; padding:9px; }
 .timeline-dot { width:9px; height:9px; }
}
"""
css_path.write_text(css)

app = app_path.read_text()
app = once(app, 'const timelineButton = document.querySelector("#timeline-button");',
"""const timelineButton = document.querySelector("#timeline-button");
const timelineListElement = document.querySelector("#timeline-list");
const newTimelineButton = document.querySelector("#new-timeline");""", "timeline UI references")
app = once(app, 'let activeView = "timeline";',
"""let activeView = "timeline";
let timelines = [];
const DEFAULT_TIMELINE_ID = "00000000000000000000000000000000";
let activeTimelineId = (() => { try { return localStorage.getItem("ferry_active_timeline") || DEFAULT_TIMELINE_ID; } catch { return DEFAULT_TIMELINE_ID; } })();
let draggingTimelineId = ""; """, "timeline state")
app = once(app, 'async function loadMessages() {',
"""async function loadTimelines() {
  const response = await authenticatedFetch("/api/v1/timelines", { cache: "no-store", signal: authController.signal });
  if (response.status === 401) { showAccess("This device is no longer connected."); return; }
  if (!response.ok) throw new Error(await readError(response));
  const payload = await response.json();
  timelines = payload.timelines || [];
  if (!timelines.some((item) => item.id === activeTimelineId)) activeTimelineId = timelines[0]?.id || DEFAULT_TIMELINE_ID;
  try { localStorage.setItem("ferry_active_timeline", activeTimelineId); } catch {}
  renderTimelineList();
}

function renderTimelineList() {
  timelineListElement.replaceChildren();
  for (const item of timelines) {
    const row = document.createElement("div");
    row.className = "timeline-row" + (item.id === activeTimelineId ? " is-active" : "");
    row.dataset.timelineId = item.id;
    row.draggable = true;
    row.setAttribute("role", "listitem");
    const select = document.createElement("button");
    select.type = "button"; select.className = "timeline-select";
    const dot = document.createElement("span"); dot.className = "timeline-dot";
    const name = document.createElement("span"); name.textContent = item.name;
    select.append(dot, name);
    select.addEventListener("click", () => selectTimeline(item.id));
    const menu = document.createElement("button");
    menu.type = "button"; menu.className = "timeline-menu"; menu.textContent = "•••";
    menu.setAttribute("aria-label", "Timeline options");
    menu.addEventListener("click", () => {
      const action = prompt("Enter: r to rename, d to delete", "r");
      if (action?.toLowerCase() === "r") renameTimeline(item);
      if (action?.toLowerCase() === "d") deleteTimeline(item);
    });
    row.append(select, menu);
    row.addEventListener("dragstart", (event) => { draggingTimelineId = item.id; event.dataTransfer.effectAllowed = "move"; });
    row.addEventListener("dragover", (event) => { event.preventDefault(); event.dataTransfer.dropEffect = "move"; });
    row.addEventListener("drop", async (event) => {
      event.preventDefault();
      const from = draggingTimelineId; const to = item.id; draggingTimelineId = "";
      if (!from || from === to) return;
      const ordered = [...timelines]; const a = ordered.findIndex((v) => v.id === from); const b = ordered.findIndex((v) => v.id === to);
      const [moved] = ordered.splice(a, 1); ordered.splice(b, 0, moved);
      await saveTimelineOrder(ordered);
    });
    row.addEventListener("dragend", () => { draggingTimelineId = ""; });
    timelineListElement.append(row);
  }
}

async function saveTimelineOrder(ordered) {
  const response = await authenticatedFetch("/api/v1/timelines/order", { method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ids:ordered.map((v)=>v.id)}), signal:authController.signal });
  if (!response.ok) throw new Error(await readError(response));
  await loadTimelines();
}

async function selectTimeline(id) {
  if (id === activeTimelineId) return;
  activeTimelineId = id; try { localStorage.setItem("ferry_active_timeline", id); } catch {}
  renderTimelineList(); resetTimeline(); await loadMessages();
}

async function createTimeline() {
  const name = prompt("New timeline name", "New timeline");
  if (!name?.trim()) return;
  const response = await authenticatedFetch("/api/v1/timelines", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({name}), signal:authController.signal });
  if (!response.ok) { alert(await readError(response)); return; }
  const item = await response.json(); await loadTimelines(); await selectTimeline(item.id);
}

async function renameTimeline(item) {
  const name = prompt("Rename timeline", item.name);
  if (!name?.trim() || name.trim() === item.name) return;
  const response = await authenticatedFetch("/api/v1/timelines/"+item.id, { method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({name}), signal:authController.signal });
  if (!response.ok) { alert(await readError(response)); return; }
  await loadTimelines();
}

async function deleteTimeline(item) {
  if (item.id === DEFAULT_TIMELINE_ID) { alert("The default timeline cannot be deleted."); return; }
  if (!confirm('Delete "'+item.name+'"? Its messages and files will be moved to the default Timeline.')) return;
  const response = await authenticatedFetch("/api/v1/timelines/"+item.id, { method:"DELETE", signal:authController.signal });
  if (!response.ok) { alert(await readError(response)); return; }
  if (activeTimelineId === item.id) { activeTimelineId = DEFAULT_TIMELINE_ID; try { localStorage.setItem("ferry_active_timeline", activeTimelineId); } catch {} resetTimeline(); }
  await loadTimelines(); await loadMessages();
}

newTimelineButton.addEventListener("click", createTimeline);

async function loadMessages() {""", "timeline client functions")
app = once(app,
'const response = await authenticatedFetch(`/api/v1/messages?after=${cursor}&after_retraction=${retractionCursor}&limit=200`',
'const response = await authenticatedFetch(`/api/v1/messages?timeline_id=${encodeURIComponent(timelineId)}&after=${cursor}&after_retraction=${retractionCursor}&limit=200`', "timeline message query")
app = once(app, 'headers: { "Content-Type": "application/json" },\n    body: JSON.stringify({ text }),',
'headers: { "Content-Type": "application/json", "X-Ferry-Timeline-ID": activeTimelineId },\n    body: JSON.stringify({ text }),', "text timeline header")
app = once(app, 'const response = await authenticatedFetch("/api/v1/messages/file", { method: "POST", body: form, signal: authController.signal });',
'const response = await authenticatedFetch("/api/v1/messages/file", { method: "POST", headers: { "X-Ferry-Timeline-ID": activeTimelineId }, body: form, signal: authController.signal });', "file timeline header")
app = once(app, 'showApp(payload.device);\n    await loadMessages();',
'showApp(payload.device);\n    await loadTimelines();\n    await loadMessages();', "session timeline initialization")
app = once(app, 'showApp(payload.device);\n  await loadMessages();',
'showApp(payload.device);\n  await loadTimelines();\n  await loadMessages();', "join timeline initialization")
app_path.write_text(app)
print("Ferry multi-timeline patch applied.")
