from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yt_dlp

from .jobs import jobs


DEFAULT_OUTPUT_DIR = Path.home() / "Downloads" / "MyToolsVideos"
SUPPORTED_COOKIE_SOURCES = {"none", "chrome"}
MAC_COMPATIBLE_FORMAT = (
    "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/"
    "bv*[vcodec^=avc1]+ba/"
    "b[vcodec^=avc1][acodec^=mp4a]/"
    "b[vcodec^=avc1]/"
    "bv*[vcodec!*=av01][vcodec!*=vp9]+ba/"
    "b"
)


class DownloadError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def normalize_cookie_source(cookie_source: str | None) -> str:
    source = cookie_source or "none"
    if source not in SUPPORTED_COOKIE_SOURCES:
        raise DownloadError("不支持这个登录状态选项，请选择“不使用登录状态”或“读取 Chrome 登录状态”。")
    return source


def validate_url(url: str) -> str:
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DownloadError("请输入有效的 http 或 https 视频链接。")
    return value


def safe_output_dir(output_dir: str | None) -> Path:
    if not output_dir or not output_dir.strip():
        return DEFAULT_OUTPUT_DIR
    return Path(output_dir).expanduser()


def readable_error(exc: BaseException) -> str:
    text = str(exc).strip()
    if "Unsupported URL" in text:
        return "这个网站或链接格式暂时不支持。"
    if "Private video" in text or "login" in text.lower():
        return "这个视频可能需要登录。请先在 Chrome 里登录对应网站，然后选择“读取 Chrome 登录状态”。"
    if "DRM" in text.upper():
        return "这个视频可能有 DRM 版权保护，这个工具无法下载。"
    if text:
        return re.sub(r"\s+", " ", text)
    return exc.__class__.__name__


def ffprobe_streams(path: Path) -> list[dict[str, Any]]:
    if not shutil.which("ffprobe"):
        return []

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,pix_fmt",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    import json

    return json.loads(result.stdout).get("streams") or []


def is_mac_playable_mp4(path: Path) -> bool:
    streams = ffprobe_streams(path)
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video:
        return False

    video_ok = video.get("codec_name") == "h264" and video.get("pix_fmt") in {None, "yuv420p"}
    audio_ok = audio is None or audio.get("codec_name") in {"aac", "mp3", "alac"}
    return video_ok and audio_ok


def transcode_for_mac(path: Path) -> None:
    if not ffmpeg_available():
        raise DownloadError("需要 ffmpeg 才能转换成 Mac 可播放的视频。请先运行：brew install ffmpeg")

    temp_path = path.with_name(f"{path.stem}.mac-compatible.tmp.mp4")
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(temp_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        temp_path.replace(path)
    except subprocess.CalledProcessError as exc:
        temp_path.unlink(missing_ok=True)
        raise DownloadError(readable_error(exc)) from exc


def ydl_options(cookie_source: str, *, quiet: bool = True) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": quiet,
        "no_warnings": quiet,
        "noplaylist": True,
        "ignoreerrors": False,
    }
    if cookie_source == "chrome":
        opts["cookiesfrombrowser"] = ("chrome",)
    return opts


def probe_url(url: str, cookie_source: str | None = None) -> dict[str, Any]:
    url = validate_url(url)
    cookie_source = normalize_cookie_source(cookie_source)
    options = ydl_options(cookie_source)
    options["skip_download"] = True

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise DownloadError(readable_error(exc)) from exc

    if not info:
        raise DownloadError("没有解析到视频信息。")

    formats = info.get("formats") or []
    return {
        "title": info.get("title"),
        "extractor": info.get("extractor"),
        "webpage_url": info.get("webpage_url") or url,
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel"),
        "format_count": len(formats),
        "ffmpeg_available": ffmpeg_available(),
    }


def download_url(
    *,
    job_id: str,
    url: str,
    cookie_source: str | None,
    quality: str | None,
    output_dir: str | None,
) -> None:
    try:
        url = validate_url(url)
        cookie_source = normalize_cookie_source(cookie_source)
        destination = safe_output_dir(output_dir)
        destination.mkdir(parents=True, exist_ok=True)

        jobs.update(job_id, status="running", message="Preparing download")

        def progress_hook(data: dict[str, Any]) -> None:
            status = data.get("status")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                downloaded = data.get("downloaded_bytes")
                progress = 0.0
                if total and downloaded:
                    progress = max(0.0, min(100.0, downloaded / total * 100.0))
                jobs.update(
                    job_id,
                    status="running",
                    progress=progress,
                    message="Downloading",
                    downloaded_bytes=downloaded,
                    total_bytes=total,
                    speed=data.get("speed"),
                    eta=data.get("eta"),
                )
            elif status == "finished":
                jobs.update(
                    job_id,
                    status="running",
                    progress=99.0,
                    message="Merging and finalizing",
                    output_path=data.get("filename"),
                )

        selected_format = MAC_COMPATIBLE_FORMAT if (quality or "best") == "best" else MAC_COMPATIBLE_FORMAT
        options = ydl_options(cookie_source)
        options.update(
            {
                "format": selected_format,
                "outtmpl": str(destination / "%(title).180B [%(id)s].%(ext)s"),
                "merge_output_format": "mp4",
                "progress_hooks": [progress_hook],
                "windowsfilenames": True,
                "restrictfilenames": False,
            }
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            output_path = None
            if info:
                output_path = ydl.prepare_filename(info)
                if options.get("merge_output_format"):
                    output_path = str(Path(output_path).with_suffix(".mp4"))

        if output_path:
            final_path = Path(output_path)
            if final_path.exists() and not is_mac_playable_mp4(final_path):
                jobs.update(
                    job_id,
                    status="running",
                    progress=99.0,
                    message="Converting to Mac-compatible H.264 MP4",
                )
                transcode_for_mac(final_path)

        jobs.update(
            job_id,
            status="completed",
            progress=100.0,
            title=info.get("title") if info else None,
            output_path=output_path,
            message="Completed",
        )
    except Exception as exc:
        jobs.update(
            job_id,
            status="error",
            error=readable_error(exc),
            message="Failed",
        )
