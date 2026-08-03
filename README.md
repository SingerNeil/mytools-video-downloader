# MyTools Video Downloader

一个面向 Windows 10/11 与 macOS 的本地视频下载与压缩工具。它提供清晰的中文网页界面，支持粘贴视频链接或整段分享文案，能够下载单个视频、播放列表和 B 站多 P/合集，并将结果转换成两个系统都容易播放的 MP4 文件。

目前重点适配：

- 哔哩哔哩
- YouTube
- 抖音
- 小红书
- 其他能够被 [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) 解析的网站

> 请只下载你有权访问和保存的内容，并遵守网站规则及所在地法律。DRM 保护、地区限制、已失效或账号无权访问的内容无法通过本工具绕过限制。

## 最快开始

### Windows 10/11

先打开 PowerShell 或 Windows Terminal 安装运行环境：

```powershell
winget install --id Python.Python.3.12 --exact
winget install --id Gyan.FFmpeg --exact
winget install --id OpenJS.NodeJS.LTS --exact
```

安装完成后关闭并重新打开终端，然后执行：

```powershell
git clone https://github.com/SingerNeil/mytools-video-downloader.git
cd mytools-video-downloader
.\run.bat
```

也可以下载 GitHub ZIP，解压后直接双击 `run.bat`。

### macOS

先安装 [Homebrew](https://brew.sh/)，然后执行：

```bash
brew install python@3.12 ffmpeg node
git clone https://github.com/SingerNeil/mytools-video-downloader.git
cd mytools-video-downloader
chmod +x run.sh
./run.sh
```

启动脚本会自动创建 `.venv`、安装或更新 Python 依赖，并在本机启动服务。看到下面的地址后，用浏览器打开它：

```text
http://127.0.0.1:8765
```

保持启动窗口运行。需要停止服务时，在该窗口按 `Ctrl+C`。

## 下载 B 站最高画质

B 站的 1080P 高码率、4K、8K、HDR、杜比等画质是否可用，取决于视频提供的格式以及登录账号本身的观看权限。未登录时通常只能取得公开视频画质。

推荐使用工具内置的扫码登录：

1. 启动工具并打开网页。
2. 在“登录状态”中选择“扫码登录 B 站（最高画质推荐）”。
3. 点击“生成登录二维码”。
4. 使用哔哩哔哩手机客户端扫码并在手机上确认。
5. 页面显示账号昵称和会员状态后，粘贴 B 站视频链接。
6. 选择“最高可用画质”。
7. 点击“检测链接”，确认识别结果后开始下载。

扫码登录的 Cookie：

- 只保存在当前 Python 进程的内存中；
- 不会写入 `user_settings.json` 或其他 Cookie 文件；
- 不会通过登录状态接口返回给网页；
- 仅作用于 `bilibili.com` 及其 API 子域；
- 点击退出登录或停止工具后立即失效。

如果不想扫码，也可以选择读取 Firefox 或 Chrome 的现有登录状态。Windows 推荐 Firefox；Chrome 在 Windows 上经常锁定 Cookie 数据库，如需读取 Chrome 登录状态，请先彻底退出 Chrome，包括任务管理器中的后台 `chrome.exe`。

## 基本使用

主页面分为视频下载、任务状态和本地视频压缩三个区域，下载过程与文件保存位置会直接显示在页面中。

1. 粘贴视频网址或带网址的分享文案。
2. 工具会自动提取第一个有效链接并识别平台。
3. 选择登录状态、下载范围、画质、上传压缩大小和保存位置。
4. 点击“检测链接”查看标题与解析结果。
5. 点击“开始下载”。
6. 等待状态变为“已完成”，在页面显示的保存位置查看文件。

页面中的“停止任务”只停止当前下载或转码任务，不会关闭本地服务。

### 下载范围

- `仅下载当前视频`：适合普通单视频链接。
- `下载整个合集/列表`：适合 YouTube 播放列表、B 站多 P、B 站合集，以及解析器支持的其他列表。

合集会自动保存在以合集标题命名的子目录中。

### 画质选项

- `最高可用画质`：选择当前链接与账号权限下可获得的最高视频和音频流。
- `优先 60 帧`：优先选择 50 FPS 以上的视频流，不存在时自动回退。
- `4320P / 8K`、`2160P / 4K`、`1440P / 2K`：限制最高视频高度。
- `1080P`、`720P`、`480P`、`360P`：适合控制文件大小和处理时间。

高画质网站通常将视频流和音频流分开提供。工具会自动下载、合并，并在需要时转换为 H.264/AAC MP4：

- macOS 优先尝试 VideoToolbox 硬件编码，失败后回退到 `libx264`；
- Windows 默认使用兼容性稳定的 `libx264`；
- 高分辨率或长视频的合并与转码可能明显慢于下载过程。

### 抖音与小红书

可以直接粘贴分享文案，无需手动提取其中的短链接。抖音 `/user/self?modal_id=...` 链接会自动转换为对应的视频地址。

Windows 下载抖音时会优先使用一个隔离的 Microsoft Edge 无头页面，让抖音网页自行完成当前接口所需的签名，再把页面返回的视频格式交给下载引擎。这个流程不会读取正在运行的 Chrome Cookie 数据库，因此 Chrome 无需退出，也不要求安装 Firefox。macOS 会先尝试常规解析，失败后再使用本机 Chrome 或 Edge 执行同样的页面回退。

公开内容选择“不使用登录状态”即可。`/user/self?...&modal_id=...` 这类从“我的喜欢”页面复制的链接，只要对应视频本身可公开访问，也可以直接下载。私密、仅登录账号可见或需要人工验证码的内容仍可能无法自动处理。

## 视频压缩

### 下载后生成上传版

下载时可以选择额外生成约 50 MB、25 MB 或 15 MB 的上传版：

- 原始下载文件仍会保留；
- 额外生成最高 720P 的 H.264/AAC MP4；
- 文件名会带有 `[适合上传-目标大小MB]`；
- 目标大小是估算值，实际结果可能略有差异。

### 压缩本地文件

网页下方可以选择本机的 MP4、MOV、M4V、MKV 或 WEBM 文件进行压缩。处理结果保存到当前设置的下载目录，原始文件不会被修改。

## 保存位置

默认目录：

```text
Windows: C:\Users\<用户名>\Downloads\MyToolsVideos
macOS:   /Users/<用户名>/Downloads/MyToolsVideos
```

在页面中修改保存位置后，工具会在项目根目录创建 `user_settings.json`。该文件只记录本机下载目录，已经被 `.gitignore` 排除，不会提交到 Git。

Windows 文件名中的保留字符及 `CON`、`NUL`、`LPT1` 等系统保留名称会被自动清理。

## 启动脚本做了什么

Windows 的 `run.bat` 会调用 `run.ps1`；macOS 使用 `run.sh`。脚本会：

1. 检查 Python 版本是否至少为 3.10；
2. 创建或复用当前系统的 `.venv`；
3. 根据 `requirements.txt` 安装或更新依赖；
4. 检查 ffmpeg、ffprobe 和 Node.js；
5. 使用 Uvicorn 启动 FastAPI 服务。

如果电脑上有多个 Python，可以显式指定解释器。

Windows PowerShell：

```powershell
$env:PYTHON_BIN = "C:\Path\To\Python312\python.exe"
.\run.bat
```

macOS：

```bash
PYTHON_BIN=/path/to/python3.12 ./run.sh
```

## 更新项目

如果使用 Git clone：

```bash
git pull
```

然后重新运行 `run.bat` 或 `./run.sh`。启动脚本会根据最新的 `requirements.txt` 自动更新 Python 依赖。

## 常见问题

### 页面无法打开

确认启动窗口仍在运行，并显示类似内容：

```text
Uvicorn running on http://127.0.0.1:8765
```

如果 `8765` 端口已被其他程序占用，请先关闭旧的工具进程，再重新启动。

### 提示没有 ffmpeg 或 ffprobe

Windows：

```powershell
winget install --id Gyan.FFmpeg --exact
```

macOS：

```bash
brew install ffmpeg
```

安装后必须重新打开终端，使 `PATH` 更新，然后再次启动工具。

### B 站只能下载 480P 或 720P

依次检查：

1. 是否选择了“扫码登录 B 站”；
2. 页面是否已经显示登录账号；
3. 手机是否完成了确认，而不只是扫描二维码；
4. 是否选择了“最高可用画质”；
5. 账号是否有权在 B 站网页端播放目标画质；
6. `yt-dlp` 是否已通过重新运行启动脚本更新。

退出工具会清除扫码登录状态，下次启动需要重新扫码。

### Windows 读取 Chrome Cookie 失败

抖音公开链接不需要读取 Chrome Cookie，选择“不使用登录状态”即可触发 Edge 自动解析。其他网站优先改用内置的 B 站扫码登录或 Firefox；确实需要 Chrome 时，请完全退出 Chrome，并在任务管理器中确认所有 `chrome.exe` 进程都已结束。

### YouTube 提示没有可用格式

安装 Node.js 22+，关闭并重新启动工具：

```powershell
winget install --id OpenJS.NodeJS.LTS --exact
```

YouTube 的页面解析规则变化较快，也应确保启动时安装到了最新允许版本的 `yt-dlp`。

### 任务长时间停在 95% 附近

这通常不是下载卡死，而是正在合并音视频、转换为通用 MP4，或生成上传压缩版。4K、8K 和长视频需要更多时间；页面会继续显示媒体处理进度。连续约 5 分钟没有任何媒体进度时，工具会自动停止该处理步骤并报告错误。

### 出现 `moov atom not found` 或文件损坏

工具会检查不可读取的媒体文件，清理本次产生的半成品并自动重试一次。YouTube 使用 MKV 作为中间合并容器，以降低高画质合并时生成损坏 MP4 的概率。

### Windows 提示现有 `.venv` 不是有效环境

`.venv` 不能在 Windows 与 macOS 之间共用。删除项目中的 `.venv` 后，在当前系统重新运行启动脚本即可创建新的环境。不要把 `.venv` 提交到 Git 或放进发布压缩包。

## 开发与测试

项目结构：

```text
app/                  FastAPI 接口、下载任务、B 站登录和设置
static/               本地网页界面
tests/                自动化测试
run.bat / run.ps1     Windows 启动入口
run.sh                macOS 启动入口
requirements.txt      Python 依赖
```

安装依赖后运行测试：

Windows：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check static\app.js
```

macOS：

```bash
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
```

本地 API：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 运行环境、保存目录和 B 站登录摘要 |
| `GET` | `/api/bilibili/auth` | 查询不含 Cookie 的 B 站登录状态 |
| `POST` | `/api/bilibili/auth/qr` | 生成 B 站登录二维码 |
| `GET` | `/api/bilibili/auth/qr/{qr_key}` | 查询扫码状态 |
| `POST` | `/api/bilibili/auth/logout` | 清除内存中的 B 站登录信息 |
| `POST` | `/api/settings` | 保存下载目录 |
| `POST` | `/api/probe` | 检测和解析链接 |
| `POST` | `/api/download` | 创建下载任务 |
| `POST` | `/api/compress-local` | 上传并压缩本地视频 |
| `GET` | `/api/jobs/{job_id}` | 查询任务状态 |
| `POST` | `/api/jobs/{job_id}/cancel` | 停止任务 |

## 隐私与安全

- 服务默认只监听 `127.0.0.1`，不会主动开放到局域网或公网。
- B 站扫码 Cookie 仅保存在内存中，并使用 `.bilibili.com` 域级作用域提供给下载引擎。
- 浏览器登录模式由 `yt-dlp` 直接读取本机浏览器 Cookie，本工具不会收集用户名或密码。
- 上传本地视频进行压缩时，临时文件保存在项目的 `.mytools_uploads` 中，任务结束后会清理。
- 不要将服务端口暴露到公网，也不要向他人提供包含登录状态的运行环境。

## 技术实现与致谢

- Web 服务：[FastAPI](https://fastapi.tiangolo.com/)
- 下载与网站解析：[yt-dlp](https://github.com/yt-dlp/yt-dlp)
- 音视频处理：[FFmpeg](https://ffmpeg.org/)
- B 站扫码登录、会员状态展示和画质档位设计参考了 MIT 许可的 [BilibiliVideoDownload](https://github.com/BilibiliVideoDownload/BilibiliVideoDownload) 项目
- 抖音浏览器回退思路参考了 MIT 许可的 [douyin-downloader](https://github.com/jiji262/douyin-downloader) 项目

本项目使用自己的 FastAPI 后端、原生网页界面和 `yt-dlp` 下载流程实现上述功能。
