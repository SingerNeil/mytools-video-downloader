from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .downloader import DEFAULT_OUTPUT_DIR


ROOT_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT_DIR / "user_settings.json"


def normalize_output_dir(output_dir: str | None) -> str:
    if not output_dir or not output_dir.strip():
        return str(DEFAULT_OUTPUT_DIR)
    return str(Path(output_dir.strip()).expanduser())


def load_settings() -> dict[str, str]:
    default_settings = {"output_dir": str(DEFAULT_OUTPUT_DIR)}
    if not SETTINGS_PATH.exists():
        return default_settings

    try:
        raw_settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_settings

    if not isinstance(raw_settings, dict):
        return default_settings

    output_dir = normalize_output_dir(raw_settings.get("output_dir"))
    return {"output_dir": output_dir}


def save_settings(output_dir: str | None) -> dict[str, str]:
    settings: dict[str, Any] = load_settings()
    settings["output_dir"] = normalize_output_dir(output_dir)
    SETTINGS_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"output_dir": settings["output_dir"]}
