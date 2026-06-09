# Mac 端的 MyTools 视频下载工具

一个本地网页工具，用 `yt-dlp` 下载 YouTube、哔哩哔哩、小红书、抖音等站点的视频。默认下载单个视频，也可以手动选择下载整个合集/列表。

## 环境要求

- macOS，Apple Silicon 或 Intel 都可以
- Python 3.10+，这台 Mac 推荐使用 Homebrew Python 3.12
- Homebrew
- `ffmpeg`，用于合并视频和音频
- Node 22+，用于 YouTube 的 JS 挑战解析

如果页面提示缺少 `ffmpeg`，先安装：

```bash
brew install ffmpeg
```

如果 YouTube 下载提示没有可用格式，先确认 Node 已安装：

```bash
brew install node
```

## 启动

```bash
cd /Users/ming/codes/My_Tools/video_downloader
./run.sh
```

`run.sh` 会优先使用 `python3.12`。如果要指定 Python，可以这样启动：

```bash
PYTHON_BIN=/opt/homebrew/bin/python3 ./run.sh
```

打开浏览器访问：

```text
http://127.0.0.1:8765
```

## 使用

1. 粘贴视频链接。抖音这类分享文本也可以直接粘贴，工具会从文本里提取第一个视频链接。
2. 选择登录状态：
   - `不使用登录状态`：适合公开视频。
   - `读取 Chrome 登录状态`：适合你已经在 Chrome 登录后才能看的视频。
3. 查看链接来源。页面会根据你输入的链接自动切换到 `哔哩哔哩`、`YouTube`、`小红书`、`抖音` 或 `通用链接`。
4. 选择下载范围：
   - `仅下载当前视频`：只下载你输入链接指向的这个视频。
   - `下载整个合集/列表`：下载该链接所属的合集、列表或 B 站多 P 视频。
   - 页面会根据链接自动切换这个选项。例如 YouTube 播放列表、B 站多 P 链接会自动切到合集/列表；抖音、小红书普通链接会自动切到单视频。
5. 选择清晰度：
   - `最高可用画质`：选择当前账号能拿到的最高可用 MP4。
   - `优先 60 帧`：平台和账号支持时优先下载高帧率版本。
   - `1080P`、`720P`、`480P`、`360P`：限制最高视频高度。
6. 保持默认保存目录，或者输入你自己的本地目录。这个目录会被记住，下次重启工具后仍然使用。
7. 点击 `检测链接` 检查链接。
8. 点击 `开始下载`。

默认保存目录是：

```text
~/Downloads/MyToolsVideos
```

## 说明

- 默认仍然是单视频下载，避免误把整个播放列表都下载下来。
- 合集/列表下载会在你选择的保存目录下新建一个以合集标题命名的子文件夹，所有分集都放进这个子文件夹。
- 页面里修改保存目录后，会写入本地 `user_settings.json`。这个文件已加入 `.gitignore`，不会上传到 GitHub。
- 会员清晰度仍然取决于你的账号权限。需要先在 Chrome 里登录对应网站，再选择 `读取 Chrome 登录状态`。
- 抖音链接由 `yt-dlp` 的 Douyin 解析器处理。部分短链、私密视频或风控页面可能需要先在 Chrome 登录抖音，再选择 `读取 Chrome 登录状态`。
- YouTube 下载需要 `yt-dlp-ejs` 和 Node 22+ 来解析 YouTube 的 JS 挑战。`./run.sh` 会按 `requirements.txt` 自动安装 `yt-dlp[default]`，其中包含 `yt-dlp-ejs`。
- 工具不会保存用户名或密码。
- 下载优先选择 Mac 兼容的 H.264/AAC MP4。如果平台只给 AV1/VP9 等 Mac 可能只播声音的格式，工具会自动转成 Mac 可播放的 H.264 MP4。
- 部分平台页面变化很频繁。如果突然不能下载，优先更新 `yt-dlp` 及其默认依赖：

```bash
cd /Users/ming/codes/My_Tools/video_downloader
. .venv/bin/activate
python -m pip install --upgrade "yt-dlp[default]"
```

- DRM 保护、已过期、私密或暂不支持的链接可能无法下载。
