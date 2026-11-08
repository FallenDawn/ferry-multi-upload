# Ferry Multi Upload

Ferry 的浏览器多文件上传增强版，基于上游固定提交构建，不修改上游项目。

## 功能
- Android / iOS / 桌面浏览器的照片和文件选择器支持多选。
- 多个文件按顺序逐个上传，状态显示当前序号和文件名。
- 支持多个 Timeline：新建、重命名、拖拽排序、删除。\n- Timeline 列表和顺序保存在服务器 SQLite 中，所有设备共享同步。\n- 各 Timeline 的文本、图片和文件彼此隔离；删除 Timeline 前确认，内容自动迁移到默认 Timeline。\n- 每个文件独立进入当前选中的 Timeline。
- 单个文件最大支持 100 MB（前端预检 + 后端硬限制）。
- 中途失败时，已成功文件从队列移除，剩余文件可重试。
- 桌面浏览器支持向上传区域拖入多个文件。
- 保留 Ferry 原有 API、SQLite 数据结构、设备认证和 /data 数据目录。

单个文件最大 100 MB（100 MiB，按二进制容量计算）；这不是系统后台自动剪贴板同步工具。

## Docker 镜像
GitHub Actions 在 push 到 main 后自动构建 linux/amd64 并推送：

`ghcr.io/fallendawn/ferry-multi-upload:latest`

也会发布以 Git commit SHA 命名的不可变标签。

## Unraid 部署
1. 先停止原 Ferry 容器。
2. 备份 `/mnt/user/appdata/ferry`。
3. Unraid → Docker → Add Container：
   - Repository: `ghcr.io/fallendawn/ferry-multi-upload:latest`
   - Network Type: bridge
   - Host Port: `42817` → Container Port: `42817`
   - Path: `/mnt/user/appdata/ferry` → `/data`（读写）
   - `FERRY_HOST_IP`: 填 Unraid 的局域网 IPv4
   - `FERRY_LISTEN_HOST`: `0.0.0.0`
   - `FERRY_PORT`: `42817`
4. 如果 GHCR package 仍是 Private，先在 GitHub 仓库 Packages 页面把它改为 Public；否则 Unraid 需要先 docker login。
5. 不要让新旧容器同时挂载同一个数据目录。

访问：`http://UNRAID-IP:42817`

## Build
由 `.github/workflows/docker-publish.yml` 在 GitHub Actions 构建。无需在 Unraid 安装编译工具。


多 Timeline 支持已加入，包含服务器持久化、跨设备同步和消息隔离。

Timeline 列表会在设备保持连接时定期刷新，其他设备的新增、改名、排序和删除会同步显示。

切换 Timeline 时会隔离旧请求，避免旧消息串到新时间线。

Timeline synchronization and stale-request guards included in final validation.

验证脚本已修正消息请求保护逻辑。
