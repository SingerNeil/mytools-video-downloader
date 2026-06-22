from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from .downloader import (
    DownloadError,
    VIDEO_EXTENSIONS,
    compress_local_video,
    download_url,
    ffmpeg_available,
    normalize_compression_target,
    probe_url,
    safe_path_name,
    youtube_ejs_available,
)
from .jobs import jobs
from .settings import load_settings, save_settings


ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"
UPLOAD_DIR = ROOT_DIR / ".mytools_uploads"

app = FastAPI(title="MyTools Video Downloader")
executor = ThreadPoolExecutor(max_workers=2)


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheMiddleware)


class ProbeRequest(BaseModel):
    url: str = Field(min_length=1)
    cookie_source: str = "none"
    download_scope: str = "single"


class DownloadRequest(BaseModel):
    url: str = Field(min_length=1)
    cookie_source: str = "none"
    download_scope: str = "single"
    quality: str = "best"
    compression_target_mb: int = 0
    output_dir: str | None = None


class SettingsRequest(BaseModel):
    output_dir: str | None = None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, object]:
    settings = load_settings()
    return {
        "ok": True,
        "ffmpeg_available": ffmpeg_available(),
        "youtube_ejs_available": youtube_ejs_available(),
        "default_output_dir": settings["output_dir"],
    }


@app.post("/api/settings")
def update_settings(request: SettingsRequest) -> dict[str, str]:
    return save_settings(request.output_dir)


@app.post("/api/probe")
def probe(request: ProbeRequest) -> dict[str, object]:
    try:
        return probe_url(request.url, request.cookie_source, request.download_scope)
    except DownloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/download")
def download(request: DownloadRequest) -> dict[str, object]:
    settings = save_settings(request.output_dir) if request.output_dir and request.output_dir.strip() else load_settings()
    job = jobs.create(request.url)
    executor.submit(
        download_url,
        job_id=job.id,
        url=request.url,
        cookie_source=request.cookie_source,
        download_scope=request.download_scope,
        quality=request.quality,
        compression_target_mb=request.compression_target_mb,
        output_dir=settings["output_dir"],
    )
    return job.snapshot()


@app.post("/api/compress-local")
async def compress_local(
    file: UploadFile = File(...),
    compression_target_mb: int = Form(25),
    output_dir: str | None = Form(None),
) -> dict[str, object]:
    try:
        target_mb = normalize_compression_target(compression_target_mb)
    except DownloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if target_mb == 0:
        raise HTTPException(status_code=400, detail="本地视频压缩必须选择一个目标大小。")

    original_name = safe_path_name(Path(file.filename or "本地视频").name, fallback="本地视频")
    suffix = Path(original_name).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="请选择 MP4、MOV、M4V、MKV 或 WEBM 视频文件。")

    settings = save_settings(output_dir) if output_dir and output_dir.strip() else load_settings()
    upload_folder = UPLOAD_DIR / uuid4().hex
    upload_folder.mkdir(parents=True, exist_ok=True)
    upload_path = upload_folder / original_name

    try:
        with upload_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                destination.write(chunk)
    except Exception as exc:
        upload_path.unlink(missing_ok=True)
        upload_folder.rmdir()
        raise HTTPException(status_code=500, detail="读取本地视频失败，请重新选择文件。") from exc
    finally:
        await file.close()

    if not upload_path.stat().st_size:
        upload_path.unlink(missing_ok=True)
        upload_folder.rmdir()
        raise HTTPException(status_code=400, detail="选择的视频文件是空的。")

    job = jobs.create(f"local:{original_name}")
    executor.submit(
        compress_local_video,
        job_id=job.id,
        source_path=upload_path,
        original_name=original_name,
        target_mb=target_mb,
        output_dir=settings["output_dir"],
    )
    return job.snapshot()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, object]:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.snapshot()


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, object]:
    job = jobs.request_cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.snapshot()


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
