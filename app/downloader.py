from __future__ import annotations

import importlib.util
import json
import re
import select
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
SUPPORTED_QUALITIES = {"best", "60fps", "2160p", "1440p", "1080p", "720p", "480p", "360p"}
RESERVED_MAC_FILENAMES = {".", ".."}
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv", ".webm"}
DOWNLOAD_PROGRESS_LIMIT = 95.0
TRANSCODE_PROGRESS_START = 95.0
TRANSCODE_PROGRESS_END = 99.5
TRANSCODE_NO_PROGRESS_TIMEOUT_SECONDS = 300
URL_PATTERN = re.compile(r"https?://[^\s，。；、]+")
TRAILING_URL_PUNCTUATION = ".,;:!?)]}\"'，。；：！？）】」』"
DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


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


def youtube_ejs_available() -> bool:
    return shutil.which("node") is not None and importlib.util.find_spec("yt_dlp_ejs") is not None


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


def youtube_format_for_quality(quality: str | None) -> str:
    selected = normalize_quality(quality)
    if selected == "60fps":
        return "bv*[fps>=50]+ba/bv*[fps>=50]/bv*+ba/b"
    if selected.endswith("p"):
        height = int(selected.removesuffix("p"))
        return f"bv*[height<={height}]+ba/b[height<={height}]/bv*[height<={height}]/b"
    return "bv*+ba/b"


def format_for_url(quality: str | None, url: str) -> str:
    if detect_platform(url)["id"] == "youtube":
        return youtube_format_for_quality(quality)
    return format_for_quality(quality)


def extract_first_url(value: str) -> str:
    match = URL_PATTERN.search(value.strip())
    if not match:
        return value.strip()
    return match.group(0).rstrip(TRAILING_URL_PUNCTUATION)


def detect_platform(url: str) -> dict[str, str]:
    host = urlparse(url).netloc.lower()
    if any(domain in host for domain in ("douyin.com", "iesdouyin.com", "amemv.com")):
        return {"id": "douyin", "label": "抖音"}
    if any(domain in host for domain in ("bilibili.com", "b23.tv")):
        return {"id": "bilibili", "label": "哔哩哔哩"}
    if any(domain in host for domain in ("youtube.com", "youtu.be")):
        return {"id": "youtube", "label": "YouTube"}
    if any(domain in host for domain in ("xiaohongshu.com", "xhslink.com")):
        return {"id": "xiaohongshu", "label": "小红书"}
    return {"id": "generic", "label": "通用链接"}


def validate_url(url: str) -> str:
    value = extract_first_url(url)
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


def cleanup_visible_transcode_temps(destination: Path) -> None:
    for path in destination.glob("*.mac-compatible.tmp.mp4"):
        path.unlink(missing_ok=True)


def readable_error(exc: BaseException) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        text = (exc.stderr or exc.output or str(exc)).strip()
    else:
        text = str(exc).strip()
    if "Unsupported URL" in text:
        return "这个网站或链接格式暂时不支持。"
    if "n challenge solving failed" in text or "Requested format is not available" in text:
        return (
            "YouTube 没有返回可下载的视频格式。请先停止服务并重新运行 ./run.sh，"
            "确保依赖安装完成；YouTube 下载需要 Node 22+ 和 yt-dlp-ejs。"
        )
    if "Private video" in text or "login" in text.lower():
        return "这个视频可能需要登录。请先在 Chrome 里登录对应网站，然后选择“读取 Chrome 登录状态”。"
    if "DRM" in text.upper():
        return "这个视频可能有 DRM 版权保护，这个工具无法下载。"
    if text:
        return re.sub(r"\s+", " ", text)
    return exc.__class__.__name__


def is_retryable_network_error(exc: BaseException) -> bool:
    text = str(exc)
    retryable_markers = (
        "UNEXPECTED_EOF",
        "Connection reset",
        "Connection aborted",
        "Remote end closed",
        "timed out",
        "Timeout",
        "HTTP Error 500",
        "HTTP Error 502",
        "HTTP Error 503",
        "HTTP Error 504",
        "IncompleteRead",
    )
    return any(marker in text for marker in retryable_markers)


def extract_info_with_retries(
    ydl: yt_dlp.YoutubeDL,
    url: str,
    *,
    download: bool,
    job_id: str | None = None,
    message: str = "网络连接中断",
) -> dict[str, Any] | None:
    for attempt in range(1, 4):
        try:
            if job_id and jobs.is_cancel_requested(job_id):
                raise DownloadError("任务已停止。")
            return ydl.extract_info(url, download=download)
        except Exception as exc:
            if isinstance(exc, DownloadError):
                raise
            if attempt == 3 or not is_retryable_network_error(exc):
                raise
            if job_id:
                jobs.update(
                    job_id,
                    status="running",
                    message=f"{message}，正在第 {attempt + 1} 次尝试",
                )
            time.sleep(attempt * 2)
    return None


def ffprobe_media_info(path: Path) -> dict[str, Any]:
    if not shutil.which("ffprobe"):
        return {}

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,pix_fmt,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def ffprobe_streams(path: Path) -> list[dict[str, Any]]:
    return ffprobe_media_info(path).get("streams") or []


def ffprobe_duration(path: Path) -> float | None:
    duration = (ffprobe_media_info(path).get("format") or {}).get("duration")
    try:
        value = float(duration)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def is_mac_playable_mp4(path: Path) -> bool:
    streams = ffprobe_streams(path)
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video:
        return False

    video_ok = video.get("codec_name") == "h264" and video.get("pix_fmt") in {None, "yuv420p"}
    audio_ok = audio is None or audio.get("codec_name") in {"aac", "mp3", "alac"}
    return video_ok and audio_ok


def transcode_bitrate(path: Path) -> str:
    streams = ffprobe_streams(path)
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    height = int(video.get("height") or 0) if video else 0
    if height >= 2160:
        return "24M"
    if height >= 1440:
        return "16M"
    if height >= 1080:
        return "10M"
    if height >= 720:
        return "6M"
    return "3500k"


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=8)


def run_ffmpeg_with_progress(
    command: list[str],
    *,
    job_id: str,
    duration: float | None,
    message: str,
) -> None:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    last_progress_change = time.monotonic()
    last_media_seconds = 0.0
    recent_output: list[str] = []

    try:
        while True:
            if jobs.is_cancel_requested(job_id):
                terminate_process(process)
                raise DownloadError("任务已停止。")

            if process.stdout:
                ready, _, _ = select.select([process.stdout], [], [], 1.0)
            else:
                ready = []

            if ready and process.stdout:
                line = process.stdout.readline()
                if line:
                    line = line.strip()
                    if line:
                        recent_output.append(line)
                        recent_output = recent_output[-20:]

                    key, _, value = line.partition("=")
                    if key in {"out_time_ms", "out_time_us"}:
                        try:
                            media_seconds = float(value) / 1_000_000
                        except ValueError:
                            media_seconds = last_media_seconds
                        if media_seconds > last_media_seconds + 0.2:
                            last_media_seconds = media_seconds
                            last_progress_change = time.monotonic()
                        if duration:
                            transcode_percent = max(0.0, min(100.0, media_seconds / duration * 100.0))
                            progress = TRANSCODE_PROGRESS_START + (
                                TRANSCODE_PROGRESS_END - TRANSCODE_PROGRESS_START
                            ) * transcode_percent / 100.0
                            jobs.update(
                                job_id,
                                status="running",
                                progress=progress,
                                message=f"{message}（{transcode_percent:.1f}%）",
                            )
                    elif key == "progress" and value == "end":
                        jobs.update(
                            job_id,
                            status="running",
                            progress=TRANSCODE_PROGRESS_END,
                            message=f"{message}（整理文件）",
                        )

            returncode = process.poll()
            if returncode is not None:
                if process.stdout:
                    remaining = process.stdout.read()
                    if remaining:
                        recent_output.extend(line.strip() for line in remaining.splitlines() if line.strip())
                if returncode != 0:
                    raise subprocess.CalledProcessError(
                        returncode,
                        command,
                        output="\n".join(recent_output[-40:]),
                    )
                return

            if time.monotonic() - last_progress_change > TRANSCODE_NO_PROGRESS_TIMEOUT_SECONDS:
                terminate_process(process)
                raise DownloadError(
                    "转换阶段超过 5 分钟没有任何进度，已自动停止。"
                    "可以重试，或者先选择 1080P/1440P 降低转码压力。"
                )
    except Exception:
        terminate_process(process)
        raise


def transcode_command(path: Path, temp_path: Path, *, hardware: bool) -> list[str]:
    encoder_args = (
        [
            "-c:v",
            "h264_videotoolbox",
            "-b:v",
            transcode_bitrate(path),
            "-profile:v",
            "high",
        ]
        if hardware
        else [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
        ]
    )
    return [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostats",
        "-stats_period",
        "1",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        *encoder_args,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        str(temp_path),
    ]


def transcode_for_mac(path: Path, job_id: str) -> Path:
    if not ffmpeg_available():
        raise DownloadError("需要 ffmpeg 才能转换成 Mac 可播放的视频。请先运行：brew install ffmpeg")

    final_path = path if path.suffix.lower() == ".mp4" else path.with_suffix(".mp4")
    temp_dir = final_path.parent / ".mytools_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{final_path.stem}.mac-compatible.tmp.mp4"
    temp_path.unlink(missing_ok=True)
    duration = ffprobe_duration(path)
    message = "正在转换为 Mac 可播放 MP4"

    try:
        jobs.update(
            job_id,
            status="running",
            progress=TRANSCODE_PROGRESS_START,
            message=f"{message}（准备中，4K 视频可能需要较长时间）",
            output_path=str(final_path),
        )
        try:
            run_ffmpeg_with_progress(
                transcode_command(path, temp_path, hardware=True),
                job_id=job_id,
                duration=duration,
                message=message,
            )
        except subprocess.CalledProcessError as hardware_exc:
            temp_path.unlink(missing_ok=True)
            jobs.update(
                job_id,
                status="running",
                progress=TRANSCODE_PROGRESS_START,
                message=f"{message}（硬件转码失败，改用兼容模式）",
            )
            run_ffmpeg_with_progress(
                transcode_command(path, temp_path, hardware=False),
                job_id=job_id,
                duration=duration,
                message=message,
            )
        temp_path.replace(final_path)
        if final_path != path:
            path.unlink(missing_ok=True)
        jobs.update(
            job_id,
            status="running",
            progress=TRANSCODE_PROGRESS_END,
            message=f"{message}（整理文件）",
            output_path=str(final_path),
        )
        return final_path
    except subprocess.CalledProcessError as exc:
        temp_path.unlink(missing_ok=True)
        raise DownloadError(readable_error(exc)) from exc
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def ydl_options(
    cookie_source: str,
    download_scope: str = "single",
    *,
    quiet: bool = True,
    url: str | None = None,
) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": quiet,
        "no_warnings": quiet,
        "noplaylist": download_scope == "single",
        "ignoreerrors": False,
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 5,
        "file_access_retries": 5,
        "socket_timeout": 30,
        "http_headers": DEFAULT_HTTP_HEADERS.copy(),
    }
    platform_id = detect_platform(url)["id"] if url else None
    if platform_id == "douyin":
        opts["http_headers"]["Referer"] = "https://www.douyin.com/"
    if platform_id == "youtube" and shutil.which("node"):
        opts["js_runtimes"] = {"node": {}}
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
    options = ydl_options(cookie_source, download_scope, url=url)
    options["skip_download"] = True

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = extract_info_with_retries(ydl, url, download=False)
    except Exception as exc:
        raise DownloadError(readable_error(exc)) from exc

    if not info:
        raise DownloadError("没有解析到视频信息。")

    formats = info.get("formats") or []
    entries = list(info.get("entries") or [])
    entry_count = len(entries)
    return {
        "title": info.get("title"),
        "extractor": info.get("extractor"),
        "webpage_url": info.get("webpage_url") or url,
        "platform": detect_platform(url),
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

        progress_context = {"index": 0, "total": 1}

        def progress_hook(data: dict[str, Any]) -> None:
            if jobs.is_cancel_requested(job_id):
                raise DownloadError("任务已停止。")

            status = data.get("status")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                downloaded = data.get("downloaded_bytes")
                item_progress = 0.0
                if total and downloaded:
                    item_progress = max(0.0, min(100.0, downloaded / total * 100.0))
                if progress_context["total"] > 1:
                    progress = (
                        (progress_context["index"] - 1 + item_progress / 100.0)
                        / progress_context["total"]
                        * DOWNLOAD_PROGRESS_LIMIT
                    )
                    status_message = f"正在下载第 {progress_context['index']}/{progress_context['total']} 个视频"
                else:
                    progress = item_progress * DOWNLOAD_PROGRESS_LIMIT / 100.0
                    status_message = "正在下载"
                jobs.update(
                    job_id,
                    status="running",
                    progress=progress,
                    message=status_message,
                    downloaded_bytes=downloaded,
                    total_bytes=total,
                    speed=data.get("speed"),
                    eta=data.get("eta"),
                )
            elif status == "finished":
                if progress_context["total"] > 1:
                    progress = progress_context["index"] / progress_context["total"] * DOWNLOAD_PROGRESS_LIMIT
                else:
                    progress = DOWNLOAD_PROGRESS_LIMIT
                jobs.update(
                    job_id,
                    status="running",
                    progress=progress,
                    message="正在合并并整理文件",
                    output_path=data.get("filename"),
                )

        selected_format = format_for_url(quality, url)
        entry_urls: list[str] = []
        playlist_info: dict[str, Any] | None = None
        if download_scope == "collection":
            probe_options = ydl_options(cookie_source, download_scope, url=url)
            probe_options["skip_download"] = True
            with yt_dlp.YoutubeDL(probe_options) as ydl:
                playlist_info = extract_info_with_retries(
                    ydl,
                    url,
                    download=False,
                    job_id=job_id,
                    message="解析合集时网络连接中断",
                )
            destination = collection_output_dir(base_destination, playlist_info.get("title") if playlist_info else None)
            entries = list(playlist_info.get("entries") or []) if playlist_info else []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                entry_url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
                if isinstance(entry_url, str) and urlparse(entry_url).scheme in {"http", "https"}:
                    entry_urls.append(entry_url)
        else:
            destination = base_destination

        if len(entry_urls) <= 1:
            entry_urls = []

        destination.mkdir(parents=True, exist_ok=True)
        cleanup_visible_transcode_temps(destination)
        started_at = time.time()
        options = ydl_options(cookie_source, "single" if entry_urls else download_scope, url=url)
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

        info: dict[str, Any] | None = playlist_info
        output_path = None
        with yt_dlp.YoutubeDL(options) as ydl:
            if entry_urls:
                progress_context["total"] = len(entry_urls)
                for index, entry_url in enumerate(entry_urls, start=1):
                    progress_context["index"] = index
                    if jobs.is_cancel_requested(job_id):
                        raise DownloadError("任务已停止。")
                    jobs.update(
                        job_id,
                        status="running",
                        message=f"正在下载第 {index}/{len(entry_urls)} 个视频",
                    )
                    extract_info_with_retries(
                        ydl,
                        entry_url,
                        download=True,
                        job_id=job_id,
                        message=f"第 {index}/{len(entry_urls)} 个视频连接中断",
                    )
                output_path = str(destination)
            else:
                info = extract_info_with_retries(
                    ydl,
                    url,
                    download=True,
                    job_id=job_id,
                    message="下载视频时网络连接中断",
                )
                output_path = ydl.prepare_filename(info)
                if options.get("merge_output_format"):
                    output_path = str(Path(output_path).with_suffix(".mp4"))

        include_existing_collection_files = download_scope == "collection" and bool(entry_urls)
        final_paths = sorted(
            path
            for path in destination.iterdir()
            if path.is_file() and (include_existing_collection_files or path.stat().st_mtime >= started_at - 1)
            and path.suffix.lower() in VIDEO_EXTENSIONS
        )
        if output_path and Path(output_path).is_file() and Path(output_path) not in final_paths:
            final_paths.append(Path(output_path))

        if final_paths:
            output_path = str(destination) if download_scope == "collection" else str(final_paths[0])

        for index, final_path in enumerate(final_paths):
            if not is_mac_playable_mp4(final_path):
                jobs.update(
                    job_id,
                    status="running",
                    progress=TRANSCODE_PROGRESS_START,
                    message="正在转换为 Mac 可播放 MP4",
                )
                final_paths[index] = transcode_for_mac(final_path, job_id)

        if final_paths:
            output_path = str(destination) if download_scope == "collection" else str(final_paths[0])

        jobs.update(
            job_id,
            status="completed",
            progress=100.0,
            title=info.get("title") if info else None,
            output_path=output_path,
            output_paths=[str(path) for path in final_paths] or ([output_path] if output_path else []),
            message="下载完成",
        )
    except Exception as exc:
        if jobs.is_cancel_requested(job_id) or str(exc).strip() == "任务已停止。":
            jobs.update(
                job_id,
                status="canceled",
                error=None,
                message="任务已停止",
            )
            return
        jobs.update(
            job_id,
            status="error",
            error=readable_error(exc),
            message="下载失败",
        )
