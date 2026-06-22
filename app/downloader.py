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
from uuid import uuid4

import yt_dlp

from .jobs import jobs


DEFAULT_OUTPUT_DIR = Path.home() / "Downloads" / "MyToolsVideos"
SUPPORTED_COOKIE_SOURCES = {"none", "chrome"}
SUPPORTED_DOWNLOAD_SCOPES = {"single", "collection"}
SUPPORTED_QUALITIES = {"best", "60fps", "2160p", "1440p", "1080p", "720p", "480p", "360p"}
SUPPORTED_COMPRESSION_TARGETS_MB = {0, 15, 25, 50}
RESERVED_MAC_FILENAMES = {".", ".."}
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv", ".webm"}
DOWNLOAD_PROGRESS_LIMIT = 95.0
TRANSCODE_PROGRESS_START = 95.0
TRANSCODE_PROGRESS_END = 99.5
COMPRESSION_PROGRESS_START = 95.0
COMPRESSION_PROGRESS_END = 99.5
TRANSCODE_NO_PROGRESS_TIMEOUT_SECONDS = 300
MAX_DOWNLOAD_ATTEMPTS = 2
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


def normalize_compression_target(target_mb: int | None) -> int:
    selected = target_mb or 0
    if selected not in SUPPORTED_COMPRESSION_TARGETS_MB:
        raise DownloadError("不支持这个压缩大小选项。")
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


def merge_output_format_for_url(url: str) -> str:
    if detect_platform(url)["id"] == "youtube":
        return "mkv"
    return "mp4"


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
    if "moov atom not found" in text or "Invalid data found when processing input" in text:
        return (
            "下载后的媒体文件不完整或已损坏，工具已避免继续转换这个坏文件。"
            "请重新点击“开始下载”；如果连续出现，建议选择“读取 Chrome 登录状态”后再试。"
        )
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


def is_readable_media_file(path: Path) -> bool:
    try:
        ffprobe_media_info(path)
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
        return False
    return True


def cleanup_invalid_downloads(paths: list[Path], *, started_at: float) -> None:
    for path in paths:
        try:
            if path.stat().st_mtime >= started_at - 1:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def ffprobe_duration(path: Path) -> float | None:
    duration = (ffprobe_media_info(path).get("format") or {}).get("duration")
    try:
        value = float(duration)
    except (TypeError, ValueError):
        value = 0.0
    if value > 0:
        return value

    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    value = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
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
    progress_start: float = TRANSCODE_PROGRESS_START,
    progress_end: float = TRANSCODE_PROGRESS_END,
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
                            progress = progress_start + (
                                progress_end - progress_start
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
                            progress=progress_end,
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
        "0:a:0?",
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


def upload_compression_command(path: Path, output_path: Path, *, duration: float, target_mb: int) -> list[str]:
    target_bits = target_mb * 1024 * 1024 * 8 * 0.88
    total_bitrate = int(target_bits / duration)
    audio_bitrate = 64_000 if total_bitrate < 600_000 else 96_000
    video_bitrate = total_bitrate - audio_bitrate
    if video_bitrate < 120_000:
        raise DownloadError(
            f"视频时长较长，无法压缩到约 {target_mb} MB。"
            "请选择更大的目标大小，或先下载较短的视频。"
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
        "0:a:0?",
        "-vf",
        "scale=w='min(iw,1280)':h='min(ih,720)':force_original_aspect_ratio=decrease:force_divisible_by=2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-b:v",
        str(video_bitrate),
        "-maxrate",
        str(int(video_bitrate * 1.15)),
        "-bufsize",
        str(video_bitrate * 2),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        str(audio_bitrate),
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        str(output_path),
    ]


def compress_for_upload(path: Path, target_mb: int, job_id: str) -> Path:
    target_mb = normalize_compression_target(target_mb)
    if target_mb == 0:
        return path
    if not ffmpeg_available():
        raise DownloadError("需要 ffmpeg 才能生成适合上传的小文件。")

    target_bytes = target_mb * 1024 * 1024
    if path.stat().st_size <= target_bytes:
        return path

    duration = ffprobe_duration(path)
    if not duration:
        raise DownloadError("无法读取视频时长，因此不能按目标大小压缩。")

    output_path = path.with_name(f"{path.stem} [适合上传-{target_mb}MB].mp4")
    temp_dir = path.parent / ".mytools_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{path.stem}.upload-{target_mb}mb.tmp.mp4"
    temp_path.unlink(missing_ok=True)
    message = f"正在压缩为约 {target_mb} MB 的上传版"

    try:
        jobs.update(
            job_id,
            status="running",
            progress=COMPRESSION_PROGRESS_START,
            message=f"{message}（原始视频会保留）",
            output_path=str(output_path),
        )
        run_ffmpeg_with_progress(
            upload_compression_command(path, temp_path, duration=duration, target_mb=target_mb),
            job_id=job_id,
            duration=duration,
            message=message,
        )
        temp_path.replace(output_path)
        jobs.update(
            job_id,
            status="running",
            progress=COMPRESSION_PROGRESS_END,
            message=f"{message}（整理文件）",
            output_path=str(output_path),
        )
        return output_path
    except subprocess.CalledProcessError as exc:
        temp_path.unlink(missing_ok=True)
        raise DownloadError(readable_error(exc)) from exc
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def available_output_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise DownloadError("同名压缩文件太多，请清理保存目录后再试。")


def compress_local_video(
    *,
    job_id: str,
    source_path: Path,
    original_name: str,
    target_mb: int,
    output_dir: str | None,
) -> None:
    try:
        target_mb = normalize_compression_target(target_mb)
        if target_mb == 0:
            raise DownloadError("本地视频压缩必须选择一个目标大小。")
        if not ffmpeg_available():
            raise DownloadError("需要 ffmpeg 才能压缩本地视频。")
        if not is_readable_media_file(source_path):
            raise DownloadError("这个文件不是可读取的视频，或视频文件已经损坏。")

        destination = safe_output_dir(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        original_path = Path(original_name)
        safe_stem = safe_path_name(original_path.stem, fallback="本地视频")
        output_path = available_output_path(
            destination / f"{safe_stem} [适合上传-{target_mb}MB].mp4"
        )
        target_bytes = target_mb * 1024 * 1024

        jobs.update(
            job_id,
            status="running",
            progress=0.0,
            title=original_name,
            message="本地视频已接收，正在分析",
        )

        if source_path.stat().st_size <= target_bytes and is_mac_playable_mp4(source_path):
            shutil.copy2(source_path, output_path)
            jobs.update(
                job_id,
                status="completed",
                progress=100.0,
                output_path=str(output_path),
                output_paths=[str(output_path)],
                message="本地视频已经小于目标大小，已复制到保存位置",
            )
            return

        duration = ffprobe_duration(source_path)
        if not duration:
            raise DownloadError("无法读取视频时长，因此不能按目标大小压缩。")

        temp_dir = destination / ".mytools_tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{uuid4().hex}.local-compress.tmp.mp4"
        message = f"正在压缩本地视频为约 {target_mb} MB"
        jobs.update(
            job_id,
            status="running",
            progress=0.0,
            message=message,
            output_path=str(output_path),
        )
        try:
            run_ffmpeg_with_progress(
                upload_compression_command(
                    source_path,
                    temp_path,
                    duration=duration,
                    target_mb=target_mb,
                ),
                job_id=job_id,
                duration=duration,
                message=message,
                progress_start=0.0,
                progress_end=99.5,
            )
            temp_path.replace(output_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        jobs.update(
            job_id,
            status="completed",
            progress=100.0,
            output_path=str(output_path),
            output_paths=[str(output_path)],
            message="本地视频压缩完成",
        )
    except Exception as exc:
        if jobs.is_cancel_requested(job_id) or str(exc).strip() == "任务已停止。":
            jobs.update(job_id, status="canceled", error=None, message="任务已停止")
            return
        jobs.update(
            job_id,
            status="error",
            error=readable_error(exc),
            message="本地视频压缩失败",
        )
    finally:
        shutil.rmtree(source_path.parent, ignore_errors=True)


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
    compression_target_mb: int | None,
    output_dir: str | None,
) -> None:
    try:
        url = validate_url(url)
        cookie_source = normalize_cookie_source(cookie_source)
        download_scope = normalize_download_scope(download_scope)
        compression_target_mb = normalize_compression_target(compression_target_mb)
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
        merge_output_format = merge_output_format_for_url(url)
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
        options = ydl_options(cookie_source, "single" if entry_urls else download_scope, url=url)
        options.update(
            {
                "format": selected_format,
                "outtmpl": str(destination / "%(title).180B [%(id)s].%(ext)s"),
                "merge_output_format": merge_output_format,
                "progress_hooks": [progress_hook],
                "windowsfilenames": True,
                "restrictfilenames": False,
            }
        )

        info: dict[str, Any] | None = playlist_info
        output_path = None
        final_paths: list[Path] = []
        for download_attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
            if download_attempt > 1:
                jobs.update(
                    job_id,
                    status="running",
                    progress=0.0,
                    message="上一次下载得到半成品文件，已清理并自动重试",
                    downloaded_bytes=None,
                    total_bytes=None,
                    speed=None,
                    eta=None,
                )
            started_at = time.time()
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
                        output_path = str(Path(output_path).with_suffix(f".{merge_output_format}"))

            include_existing_collection_files = download_scope == "collection" and bool(entry_urls)
            final_paths = sorted(
                path
                for path in destination.iterdir()
                if path.is_file() and (include_existing_collection_files or path.stat().st_mtime >= started_at - 1)
                and path.suffix.lower() in VIDEO_EXTENSIONS
            )
            if output_path and Path(output_path).is_file() and Path(output_path) not in final_paths:
                final_paths.append(Path(output_path))

            invalid_paths = [path for path in final_paths if not is_readable_media_file(path)]
            if invalid_paths and download_attempt < MAX_DOWNLOAD_ATTEMPTS:
                cleanup_invalid_downloads(invalid_paths, started_at=started_at)
                continue
            if invalid_paths:
                cleanup_invalid_downloads(invalid_paths, started_at=started_at)
                raise DownloadError(
                    "下载后的媒体文件不完整或已损坏，已清理本次生成的半成品。"
                    "请重新点击“开始下载”；如果连续出现，建议选择“读取 Chrome 登录状态”后再试。"
                )
            break

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

        if compression_target_mb:
            for index, final_path in enumerate(final_paths):
                final_paths[index] = compress_for_upload(final_path, compression_target_mb, job_id)

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
