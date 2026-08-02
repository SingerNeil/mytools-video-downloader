#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  elif [ -x /opt/homebrew/bin/python3 ]; then
    PYTHON_BIN="/opt/homebrew/bin/python3"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "Python 3.10 or newer was not found." >&2
    exit 1
  fi
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 3.10 or newer is required: $PYTHON_BIN" >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

VENV_PYTHON=".venv/bin/python"
"$VENV_PYTHON" -m pip install --disable-pip-version-check -r requirements.txt

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  if [ "$(uname -s)" = "Darwin" ]; then
    echo "Warning: ffmpeg/ffprobe not found. Install them with: brew install ffmpeg" >&2
  else
    echo "Warning: ffmpeg/ffprobe not found. Install the ffmpeg package with your system package manager." >&2
  fi
fi
if ! command -v node >/dev/null 2>&1; then
  echo "Warning: Node.js 22+ is recommended for YouTube downloads." >&2
fi

echo "Starting MyTools Video Downloader at http://127.0.0.1:8765"
"$VENV_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
