from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import yt_dlp

from .jobs import jobs


DEFAULT_OUTPUT_DIR = Path.home() / "Downloads" / "MyToolsVideos"
SUPPORTED_COOKIE_SOURCES = {"none", "chrome"}
SUPPORTED_DOWNLOAD_SCOPES = {"single", "collection"}
SUPPORTED_QUALITIES = {"best", "60fps", "1080p", "720p", "480p", "360p"}
RESERVED_MAC_FILENAMES = {".", ".."}


def mac_compatible_format(height: int | None = None, prefer_60fps: bool = False) -> str:
    height_filter = f"[height<={height}]" if height else ""
    fps_filter = "[fps>=50]" if prefer_60fps else ""
    relaxed_fps_filter = "[fps<=60]" if prefer_60fps else ""

    return (
        f"bv*{height_filter}{fps_filter}[vcodec^=avc1]+ba[acodec^=mp4a]/"
        f"bv*{height_filter}{fps_filter}[vcodec^=avc1]+ba/"
        f"bv*{height_filter}{fps_filter}[vcodec^=avc1]/"
        f"bv*{height_filter}{relaxed_fps_filter}[vcodec^=avc1]+ba[acodec^=mp4a]/"
        f"bv*{height_filter}{relaxed_fps_filter}[vcodec^=avc1]+ba/"
        f"b{height_filter}[vcodec^=avc1][acodec^=mp4a]/"
        f"b{height_filter}[vcodec^=avc1]/"
        f"bv*{height_filter}[vcodec!*=av01][vcodec!*=vp9]+ba/"
        f"b{height_filter}/"
        "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/"
        "bv*[vcodec^=avc1]+ba/"
        "b"
    )


class DownloadError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def safe_path_name(value: str | None, fallback: str = "未命名合集") -> str:
    name = (value or fallback).strip()
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name or name in RESERVED_MAC_FILENAMES:
        name = fallback
    return name[:120].rstrip(" .") or fallback


def normalize_cookie_source(cookie_source: str | None) -> str:
    source = cookie_source or "none"
    if source not in SUPPORTED_COOKIE_SOURCES:
        raise DownloadError("不支持这个登录状态选项，请选择“不使用登录状态”或“读取 Chrome 登录状态”。")
    return source


def normalize_download_scope(download_scope: str | None) -> str:
    scope = download_scope or "single"
    if scope not in SUPPORTED_DOWNLOAD_SCOPES:
        raise DownloadError("不支持这个下载范围，请选择“仅下载当前视频”或“下载整个合集/列表”。")
    return scope


def normalize_quality(quality: str | None) -> str:
    selected = quality or "best"
    if selected not in SUPPORTED_QUALITIES:
        raise DownloadError("不支持这个清晰度选项。")
    return selected


def format_for_quality(quality: str | None) -> str:
    selected = normalize_quality(quality)
    if selected == "60fps":
        return mac_compatible_format(prefer_60fps=True)
    if selected.endswith("p"):
        return mac_compatible_format(int(selected.removesuffix("p")))
    return mac_compatible_format()


def validate_url(url: str) -> str:
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DownloadError("请输入有效的 http 或 https 视频链接。")
    return value


def normalize_url_for_scope(url: str, download_scope: str) -> str:
    if download_scope != "collection":
        return url

    parsed = urlparse(url)
    if "bilibili.com" not in parsed.netloc or not re.search(r"/video/(BV|av)", parsed.path, re.IGNORECASE):
        return url

    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() != "p"]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def safe_output_dir(output_dir: str | None) -> Path:
    if not output_dir or not output_dir.strip():
        return DEFAULT_OUTPUT_DIR
    return Path(output_dir).expanduser()


def collection_output_dir(base_dir: Path, title: str | None) -> Path:
    return base_dir / safe_path_name(title)


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


def ydl_options(cookie_source: str, download_scope: str = "single", *, quiet: bool = True) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": quiet,
        "no_warnings": quiet,
        "noplaylist": download_scope == "single",
        "ignoreerrors": False,
    }
    if cookie_source == "chrome":
        opts["cookiesfrombrowser"] = ("chrome",)
    return opts


def probe_url(
    url: str,
    cookie_source: str | None = None,
    download_scope: str | None = None,
) -> dict[str, Any]:
    url = validate_url(url)
    cookie_source = normalize_cookie_source(cookie_source)
    download_scope = normalize_download_scope(download_scope)
    url = normalize_url_for_scope(url, download_scope)
    options = ydl_options(cookie_source, download_scope)
    options["skip_download"] = True

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise DownloadError(readable_error(exc)) from exc

    if not info:
        raise DownloadError("没有解析到视频信息。")

    formats = info.get("formats") or []
    entries = info.get("entries") or []
    try:
        entry_count = len(entries)
    except TypeError:
        entry_count = 0
    return {
        "title": info.get("title"),
        "extractor": info.get("extractor"),
        "webpage_url": info.get("webpage_url") or url,
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel"),
        "format_count": len(formats),
        "entry_count": entry_count,
        "download_scope": download_scope,
        "ffmpeg_available": ffmpeg_available(),
    }


def download_url(
    *,
    job_id: str,
    url: str,
    cookie_source: str | None,
    download_scope: str | None,
    quality: str | None,
    output_dir: str | None,
) -> None:
    try:
        url = validate_url(url)
        cookie_source = normalize_cookie_source(cookie_source)
        download_scope = normalize_download_scope(download_scope)
        url = normalize_url_for_scope(url, download_scope)
        base_destination = safe_output_dir(output_dir)

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

        selected_format = format_for_quality(quality)
        options = ydl_options(cookie_source, download_scope)
        if download_scope == "collection":
            probe_options = ydl_options(cookie_source, download_scope)
            probe_options["skip_download"] = True
            with yt_dlp.YoutubeDL(probe_options) as ydl:
                playlist_info = ydl.extract_info(url, download=False)
            destination = collection_output_dir(base_destination, playlist_info.get("title") if playlist_info else None)
        else:
            destination = base_destination

        destination.mkdir(parents=True, exist_ok=True)
        started_at = time.time()
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

        final_paths = sorted(
            path
            for path in destination.glob("*.mp4")
            if path.is_file() and path.stat().st_mtime >= started_at - 1
        )
        if output_path and Path(output_path).exists() and Path(output_path) not in final_paths:
            final_paths.append(Path(output_path))

        if final_paths:
            output_path = str(final_paths[0]) if len(final_paths) == 1 else str(destination)

        for final_path in final_paths:
            if not is_mac_playable_mp4(final_path):
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
            output_paths=[str(path) for path in final_paths] or ([output_path] if output_path else []),
            message="Completed",
        )
    except Exception as exc:
        jobs.update(
            job_id,
            status="error",
            error=readable_error(exc),
            message="Failed",
        )
