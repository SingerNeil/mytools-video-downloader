# MyTools Video Downloader

A local web tool for downloading a single video from supported sites such as YouTube, Bilibili, and XiaoHongShu through `yt-dlp`.

## Requirements

- macOS on Apple Silicon or Intel
- Python 3.10+; Homebrew Python 3.12 is recommended on this Mac
- Homebrew
- `ffmpeg` for merging best video and audio streams

Install `ffmpeg` if the app reports it is missing:

```bash
brew install ffmpeg
```

## Start

```bash
cd /Users/ming/codes/My_Tools/video_downloader
./run.sh
```

`run.sh` prefers `python3.12` when it is available. You can override it:

```bash
PYTHON_BIN=/opt/homebrew/bin/python3 ./run.sh
```

Open:

```text
http://127.0.0.1:8765
```

## Use

1. Paste a video URL.
2. Choose cookie mode:
   - `No cookies` for public videos.
   - `Chrome cookies` for videos you can access after logging in through Chrome.
3. Keep the default save folder or enter another local path.
4. Click `Probe` to check the link.
5. Click `Download`.

The default save folder is:

```text
~/Downloads/MyToolsVideos
```

## Notes

- This first version is intentionally single-video only.
- It does not store usernames or passwords.
- Downloads prefer H.264/AAC MP4 for Mac playback. If a platform only provides AV1/VP9 or another codec that macOS may play as audio-only, the app automatically converts the file to a Mac-compatible H.264 MP4.
- Some platforms change frequently. If downloads stop working, update `yt-dlp`:

```bash
cd /Users/ming/codes/My_Tools/video_downloader
. .venv/bin/activate
python -m pip install --upgrade yt-dlp
```

- DRM-protected, expired, private, or unsupported videos may not download.
