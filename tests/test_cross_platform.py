from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from app.downloader import (
    ffmpeg_available,
    normalize_cookie_source,
    platform_name,
    preferred_hardware_encoder,
    run_ffmpeg_with_progress,
    safe_output_dir,
    safe_path_name,
    ydl_options,
)
from app.jobs import jobs


class CrossPlatformTests(unittest.TestCase):
    def test_windows_reserved_names_are_replaced(self) -> None:
        expected_names = {
            "CON": "_CON",
            "con.txt": "_con.txt",
            "LPT1.mp4": "_LPT1.mp4",
            "aux": "_aux",
        }
        for name, expected in expected_names.items():
            with self.subTest(name=name):
                self.assertEqual(safe_path_name(name, fallback="video"), expected)

    def test_filename_removes_cross_platform_invalid_characters(self) -> None:
        self.assertEqual(safe_path_name('a<b>:c/\\d|e?f*"'), "a b c d e f")

    def test_output_dir_expands_native_environment_variables(self) -> None:
        variable = "MYTOOLS_TEST_OUTPUT_ROOT"
        with patch.dict(os.environ, {variable: str(Path.cwd())}):
            syntax = f"%{variable}%/videos" if os.name == "nt" else f"${variable}/videos"
            self.assertEqual(safe_output_dir(syntax), Path.cwd() / "videos")

    def test_ffmpeg_requires_ffprobe_too(self) -> None:
        with patch("app.downloader.shutil.which", side_effect=lambda name: "tool" if name == "ffmpeg" else None):
            self.assertFalse(ffmpeg_available())

    def test_firefox_cookie_source_is_supported(self) -> None:
        self.assertEqual(normalize_cookie_source("firefox"), "firefox")
        self.assertEqual(ydl_options("firefox")["cookiesfrombrowser"], ("firefox",))

    def test_platform_labels(self) -> None:
        with patch("app.downloader.sys.platform", "darwin"), patch("app.downloader.os.name", "posix"):
            self.assertEqual(platform_name(), "macOS")
            self.assertEqual(preferred_hardware_encoder(), "h264_videotoolbox")
        with patch("app.downloader.sys.platform", "win32"), patch("app.downloader.os.name", "nt"):
            self.assertEqual(platform_name(), "Windows")
            self.assertIsNone(preferred_hardware_encoder())

    def test_progress_pipe_reader_works_on_windows_and_posix(self) -> None:
        job = jobs.create("local:test")
        command = [
            sys.executable,
            "-u",
            "-c",
            "print('out_time_us=500000'); print('progress=end')",
        ]

        run_ffmpeg_with_progress(
            command,
            job_id=job.id,
            duration=1.0,
            message="test",
            progress_start=0.0,
            progress_end=100.0,
        )

        snapshot = jobs.get(job.id)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.progress, 100.0)


if __name__ == "__main__":
    unittest.main()
