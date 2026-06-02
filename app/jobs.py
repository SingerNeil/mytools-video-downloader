from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from threading import Lock
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass
class DownloadJob:
    id: str
    url: str
    status: str
    progress: float
    message: str
    created_at: str
    updated_at: str
    title: str | None = None
    output_path: str | None = None
    output_paths: list[str] | None = None
    error: str | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed: float | None = None
    eta: float | None = None

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, DownloadJob] = {}
        self._lock = Lock()

    def create(self, url: str) -> DownloadJob:
        job = DownloadJob(
            id=uuid4().hex,
            url=url,
            status="queued",
            progress=0.0,
            message="Queued",
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> DownloadJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **changes: Any) -> DownloadJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for key, value in changes.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = utc_now_iso()
            return job


jobs = JobStore()
