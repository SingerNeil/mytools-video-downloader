# MyTools 视频下载与压缩工具

一个运行在 macOS 本地的中文网页工具。粘贴视频链接或分享文本后，可以检测链接、选择清晰度、下载单个视频或整个合集，并将结果保存到本地。

下载引擎使用 [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)，目前针对以下平台提供支持：

- YouTube
- 哔哩哔哩
- 小红书
- 抖音
- 其他 `yt-dlp` 可以解析的视频网站

网站页面和风控规则会变化，因此除 YouTube、哔哩哔哩等常用场景外，其余平台均属于尽力支持。

## 主要功能

- 自动从分享文本中提取第一个视频链接。
- 自动识别 YouTube、哔哩哔哩、小红书和抖音链接。
- 自动判断普通单视频、YouTube 播放列表和 B 站多 P/合集链接。
- 支持仅下载当前视频或下载整个合集/列表。
- 支持最高画质、优先 60 帧、4K、2K、1080P、720P、480P 和 360P。
- 可以读取 Chrome 登录状态，下载当前账号有权限观看的内容。
- YouTube 最高画质会优先选择真实的 2K/4K 视频流。
- 自动将 AV1、VP9、WebM、MKV 等格式转换为 Mac 更容易播放的 H.264/AAC MP4。
- YouTube 使用 MKV 作为中间合并容器，避免直接合并 4K MP4 时生成损坏文件。
- 下载失败时支持网络重试、坏文件检测和半成品清理。
- 页面显示下载、合并、转码和压缩进度，并支持停止当前任务。
- 下载后可以额外生成约 50 MB、25 MB 或 15 MB 的 720P 上传版。
- 可以直接选择电脑中的视频进行压缩，原始文件不会被修改。
- 自动记住上一次使用的保存目录。
- 下载合集时自动建立以合集标题命名的子文件夹。

## 环境要求

- macOS，支持 Apple Silicon 和 Intel Mac
- Python 3.10 或更高版本，推荐 Python 3.12
- Homebrew
- `ffmpeg` 和 `ffprobe`
- Node.js 22 或更高版本，用于 YouTube 页面解析
- Chrome，可选；需要读取网站登录状态时使用

安装必要工具：

```bash
brew install python@3.12 ffmpeg node
```

确认环境：

```bash
python3.12 --version
ffmpeg -version
ffprobe -version
node --version
```

## 第一次启动

在终端运行：

```bash
cd /Users/ming/codes/My_Tools/video_downloader
./run.sh
```

`run.sh` 会自动完成以下工作：

1. 选择可用的 Python。
2. 创建或复用项目中的 `.venv` 虚拟环境。
3. 安装 `requirements.txt` 中的依赖。
4. 在 `127.0.0.1:8765` 启动本地服务。

启动成功后，在浏览器打开：

```text
http://127.0.0.1:8765
```

如需指定 Python：

```bash
PYTHON_BIN=/opt/homebrew/bin/python3.12 ./run.sh
```

## 日常使用 SOP

1. 打开终端。
2. 进入项目目录并启动：

   ```bash
   cd /Users/ming/codes/My_Tools/video_downloader
   ./run.sh
   ```

3. 保持终端窗口运行，不要关闭。
4. 浏览器访问 `http://127.0.0.1:8765`。
5. 粘贴视频链接或整段分享文本。
6. 检查页面自动识别的平台和下载范围。
7. 根据需要设置：
   - 登录状态
   - 单视频或整个合集
   - 下载清晰度
   - 是否额外生成上传压缩版
   - 保存位置
8. 可以先点击“检测链接”，确认标题和解析器。
9. 点击“开始下载”。
10. 等待页面显示“已完成”，然后到“保存文件”显示的目录查看结果。

需要停止当前任务时，点击页面中的“停止任务”。停止整个本地服务时，在启动服务的终端按 `Control + C`。

## 抖音下载

本工具可以下载 `douyin.com`、`iesdouyin.com` 和 `amemv.com` 链接，并支持直接粘贴包含抖音短链的分享文本。对于从“我的喜欢”等页面复制出的 `/user/self?modal_id=...` 链接，工具会自动转换成对应的 `/video/...` 视频地址。

推荐步骤：

1. 在抖音中复制视频分享链接或整段分享文案。
2. 直接粘贴到“视频链接”输入框。
3. 确认“链接来源”自动显示为“抖音”。
4. 普通公开视频先选择“不使用登录状态”。
5. 检测成功后开始下载。

如果短链、私密内容或风控页面无法解析：

1. 先在 Chrome 中登录抖音。
2. 回到工具，选择“读取 Chrome 登录状态”。
3. 重新检测并下载。

抖音页面和接口变化较频繁，个别链接可能需要更新 `yt-dlp` 后才能继续使用。

## 下载范围

### 仅下载当前视频

只下载输入链接直接指向的视频。普通抖音、小红书和单个 YouTube/B站视频会自动选择这个模式。

### 下载整个合集/列表

适用于：

- YouTube 播放列表
- B站多 P 视频
- B站合集或列表
- 其他解析器能够返回多个条目的链接

合集文件会保存到：

```text
保存目录/合集标题/
```

## 清晰度

- `最高可用画质`：选择当前链接和账号权限可以获得的最高画质。
- `优先 60 帧`：优先选择 50 FPS 以上的视频流，没有时回退到其他最高画质。
- `2160P / 4K`：最高限制为 2160P。
- `1440P / 2K`：最高限制为 1440P。
- `1080P`、`720P`、`480P`、`360P`：限制最高视频高度。

YouTube 的 2K/4K 通常是视频流和音频流分开下载，并可能使用 AV1、VP9 或 Opus。工具会先用 MKV 合并，再转换为 Mac 更容易播放的 H.264/AAC MP4。长视频的转换阶段可能需要较长时间，页面会持续显示进度。

会员画质和登录后内容取决于账号本身的观看权限。

## Chrome 登录状态

工具不会保存用户名或密码。“读取 Chrome 登录状态”会让 `yt-dlp` 读取当前 Mac 上 Chrome 的网站 Cookie。

使用前：

1. 在 Chrome 中登录目标网站。
2. 保持 Chrome 登录状态有效。
3. 在工具中选择“读取 Chrome 登录状态”。

当公开链接能够正常下载时，优先使用“不使用登录状态”。

## 视频压缩

### 下载后生成上传版

“上传压缩”支持：

- 不压缩
- 约 50 MB
- 约 25 MB，推荐用于上传 GPT
- 约 15 MB

选择压缩后：

- 原始下载视频仍然保留。
- 工具额外生成一个 720P、H.264/AAC MP4。
- 文件名包含 `[适合上传-目标大小MB]`。
- 实际文件大小可能与目标值略有差异。

### 压缩本地视频

页面下方的“压缩本地视频”支持：

- MP4
- MOV
- M4V
- MKV
- WEBM

选择本地文件和目标大小后点击“压缩本地视频”。文件会先上传到本机的 FastAPI 服务处理，压缩结果保存到当前“保存位置”，原始文件不会被修改。

## 保存位置

代码中的默认保存目录是：

```text
~/Downloads/MyToolsVideos
```

在页面修改保存位置后，项目会将设置写入：

```text
user_settings.json
```

该文件只保存在本机并已加入 `.gitignore`。

## API

本地服务提供以下接口：

- `GET /`：打开网页界面
- `GET /api/health`：检查 ffmpeg、YouTube 运行环境和默认目录
- `POST /api/settings`：保存下载目录
- `POST /api/probe`：检测视频链接
- `POST /api/download`：创建下载任务
- `POST /api/compress-local`：上传并压缩本地视频
- `GET /api/jobs/{job_id}`：查询任务状态
- `POST /api/jobs/{job_id}/cancel`：停止任务

## 常见问题

### 页面打不开

确认启动终端中仍然显示：

```text
Uvicorn running on http://127.0.0.1:8765
```

然后刷新 `http://127.0.0.1:8765`。

### 缺少 ffmpeg

```bash
brew install ffmpeg
```

### YouTube 没有返回可下载格式

```bash
brew install node
cd /Users/ming/codes/My_Tools/video_downloader
. .venv/bin/activate
python -m pip install --upgrade "yt-dlp[default]"
```

然后停止并重新运行 `./run.sh`。

### 抖音或小红书检测失败

- 尝试粘贴完整分享文本。
- 在 Chrome 中登录对应网站。
- 选择“读取 Chrome 登录状态”。
- 更新 `yt-dlp` 后重启工具。

### 任务停在 95% 附近

这通常表示视频已经下载完成，正在合并、转换为 Mac 兼容 MP4，或生成上传压缩版。4K 和长视频可能需要较长时间。页面会显示转换百分比；连续 5 分钟没有任何媒体进度时，工具会自动停止。

### 文件损坏或出现 `moov atom not found`

工具会检测不可读取的媒体文件、清理本次生成的半成品并自动重试一次。YouTube 使用 MKV 中间容器，以降低 4K 合并过程中生成损坏 MP4 的概率。

## 更新依赖

```bash
cd /Users/ming/codes/My_Tools/video_downloader
. .venv/bin/activate
python -m pip install --upgrade "yt-dlp[default]"
```

## 使用限制

- DRM 保护内容无法下载。
- 私密、已过期、地区限制或账号无权限的内容可能无法下载。
- 平台更新页面或接口后，可能需要等待 `yt-dlp` 更新。
- 请只下载你有权访问和保存的内容，并遵守平台规则及当地法律。
