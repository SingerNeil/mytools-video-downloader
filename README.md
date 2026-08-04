# MyTools Video Downloader

本机运行的视频下载与压缩工具。网页界面，粘贴链接即可下载哔哩哔哩、抖音、YouTube、小红书，以及其他 yt-dlp 能解析的网站，自动合并转码为通用 H.264/AAC MP4。

服务只监听 `127.0.0.1`，链接与文件都不离开你的电脑。

## 快速开始

### macOS

前置准备（一次性）：

```bash
brew install python@3.12 ffmpeg node
```

启动：

```bash
git clone https://github.com/SingerNeil/mytools-video-downloader.git
cd mytools-video-downloader
chmod +x run.sh
./run.sh
```

然后打开浏览器访问 **http://127.0.0.1:8765**。

### Windows 10/11

前置准备（一次性，PowerShell）：

```powershell
winget install --id Python.Python.3.12 --exact
winget install --id Gyan.FFmpeg --exact
winget install --id OpenJS.NodeJS.LTS --exact
```

安装后关闭并重新打开终端，然后：

```powershell
git clone https://github.com/SingerNeil/mytools-video-downloader.git
cd mytools-video-downloader
.\run.bat
```

然后打开浏览器访问 **http://127.0.0.1:8765**。

启动脚本会自动创建 `.venv`、安装 Python 依赖、检查 ffmpeg，并启动服务。保持启动窗口开着；停止服务按 `Ctrl+C`，或直接点页面右上角的「关闭服务」。

## 给 AI 助手的启动说明

如果你是一个 AI agent，需要在 clone 之后手动启动这个项目，不要依赖交互式脚本，直接用：

```bash
# macOS / Linux
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

```powershell
# Windows
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

要点：

- 服务地址固定为 `http://127.0.0.1:8765`，只监听本机；
- 系统必须装有 `ffmpeg` 和 `ffprobe`（合并音视频流、转码、压缩都依赖它们），否则功能降级；
- YouTube 下载需要 Node.js 22+ 与 `yt-dlp-ejs`（`pip install yt-dlp-ejs`）；
- 网页是 `static/` 下的原生 HTML/JS，由后端直接托管，`GET /` 返回页面；
- 主要调用链：`POST /api/probe` 检测链接 → `POST /api/download` 创建任务 → `GET /api/jobs/{job_id}` 轮询进度（每 1 秒）→ 任务 `completed` 后文件在保存目录；
- 完整接口见文末「API」一节；
- 运行测试：`.venv/bin/python -m unittest discover -s tests`（Windows 用 `.venv\Scripts\python`）。

## 基本使用

1. 粘贴视频链接，或整段分享文案（抖音、小红书的分享文本可直接粘贴，会自动提取链接）；
2. 选择画质与下载范围（单个视频 / 整个合集列表），点「先检测链接」确认；
3. 点「开始下载」，等待状态变为「已完成」；
4. 文件保存在页面显示的目录，默认 `~/Downloads/MyToolsVideos`。

常用选项：

- **B 站最高画质**（1080P 高码率 / 4K / 8K / HDR）：在「更多下载设置 → 登录状态」里选「扫码登录 B 站」，用手机 B 站 App 扫码。Cookie 只存在本次运行的进程内存中，退出即失效；
- **抖音**：公开内容选「不使用登录状态」即可，无需配置浏览器；
- **下载后额外压缩**：可再生成约 15 / 25 / 50 MB 的上传版（适合微信等场景发送），原始文件保留；
- **压缩本地视频**：页面下方选择本机视频文件，生成指定大小的小副本，原文件不修改；
- **更新**：`git pull` 后重新运行启动脚本即可。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 页面打不开 | 启动窗口还在运行且显示 Uvicorn 地址吗？服务没起来就重新运行启动脚本 |
| 提示缺 ffmpeg/ffprobe | 安装后必须重新打开终端再启动脚本 |
| B 站只能下 480P/720P | 检查是否扫码登录、画质是否选了「最高可用画质」、账号在该画质下是否有观看权限 |
| YouTube 提示没有可用格式 | 安装 Node.js 22+ 和 `yt-dlp-ejs`，重启工具 |
| 任务卡在 95% 附近 | 是正常的：正在合并音视频 / 转码 / 生成上传版，4K 和长视频会明显变慢 |

## 技术细节（可选阅读）

### 架构

FastAPI 后端 + 原生网页前端 + [yt-dlp](https://github.com/yt-dlp/yt-dlp) 下载 + FFmpeg 处理。

- `app/main.py`：FastAPI 接口与任务调度
- `app/downloader.py`：下载、画质选择、转码、压缩、错误处理
- `app/bilibili_auth.py`：B 站扫码登录（Cookie 仅存内存）
- `app/douyin_browser.py`：抖音浏览器回退解析（Playwright 加载系统 Edge/Chrome，让页面自行完成签名）
- `app/jobs.py`：任务状态
- `static/`：网页界面（`index.html` / `styles.css` / `app.js`）
- `run.bat` / `run.ps1` / `run.sh`：启动脚本（建 venv、装依赖、检查环境、启动服务）

### 下载流程

高画质网站的音频和视频流通常是分开的。工具会自动下载并合并，需要时转码为 H.264/AAC MP4：macOS 优先 VideoToolbox 硬件编码（失败回退 libx264），Windows 用兼容性稳定的 libx264。下载完成后会用 ffprobe 校验文件，坏文件自动清理并重试一次。

### API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 运行环境、保存目录和 B 站登录摘要 |
| `GET` | `/api/bilibili/auth` | 查询不含 Cookie 的 B 站登录状态 |
| `POST` | `/api/bilibili/auth/qr` | 生成 B 站登录二维码 |
| `GET` | `/api/bilibili/auth/qr/{qr_key}` | 查询扫码状态 |
| `POST` | `/api/bilibili/auth/logout` | 清除内存中的 B 站登录信息 |
| `POST` | `/api/settings` | 保存下载目录 |
| `POST` | `/api/shutdown` | 从网页关闭本地服务 |
| `POST` | `/api/probe` | 检测和解析链接 |
| `POST` | `/api/download` | 创建下载任务 |
| `POST` | `/api/compress-local` | 上传并压缩本地视频 |
| `GET` | `/api/jobs/{job_id}` | 查询任务状态 |
| `POST` | `/api/jobs/{job_id}/cancel` | 停止任务 |

### 隐私与安全

- 服务默认只监听 `127.0.0.1`；
- B 站扫码 Cookie 只保存在进程内存，不写盘、不返回给网页；
- 浏览器登录模式由 yt-dlp 直接读取本机浏览器 Cookie，工具不收集账号密码；
- 本地视频压缩的临时上传文件在任务结束后清理；
- 不要把服务端口暴露到公网。

### 开发与测试

```bash
.venv/bin/python -m unittest discover -s tests -v   # 后端测试
node --check static/app.js                          # 前端语法检查
```

### 致谢

B 站扫码登录与画质档位设计参考了 MIT 许可的 [BilibiliVideoDownload](https://github.com/BilibiliVideoDownload/BilibiliVideoDownload)；抖音浏览器回退思路参考了 MIT 许可的 [douyin-downloader](https://github.com/jiji262/douyin-downloader)。
