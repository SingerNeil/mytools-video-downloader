from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from .downloader import DownloadError, download_url, ffmpeg_available, probe_url, youtube_ejs_available
from .jobs import jobs
from .settings import load_settings, save_settings


ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"

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
