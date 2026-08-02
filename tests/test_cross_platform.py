from __future__ import annotations

import os
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yt_dlp

from app.downloader import (
    bilibili_format_for_quality,
    extract_info_with_platform_fallback,
    ffmpeg_available,
    is_playback_compatible_mp4,
    normalize_cookie_source,
    platform_name,
    preferred_hardware_encoder,
    resolve_media_tool,
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
        with patch(
            "app.downloader.resolve_media_tool",
            side_effect=lambda name: "tool" if name == "ffmpeg" else None,
        ):
            self.assertFalse(ffmpeg_available())

    def test_firefox_cookie_source_is_supported(self) -> None:
        self.assertEqual(normalize_cookie_source("firefox"), "firefox")
        self.assertEqual(ydl_options("firefox")["cookiesfrombrowser"], ("firefox",))

    def test_bilibili_qr_session_is_scoped_to_all_bilibili_subdomains(self) -> None:
        url = "https://www.bilibili.com/video/BV1xx411c7mD"
        cookie_file = StringIO(
            "# Netscape HTTP Cookie File\n"
            ".bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\ttest\n"
        )
        with patch("app.downloader.bilibili_auth.cookie_file", return_value=cookie_file):
            options = ydl_options("bilibili", url=url)

        ydl = yt_dlp.YoutubeDL(options)
        self.assertIn("SESSDATA=test", ydl.cookiejar.get_cookie_header("https://api.bilibili.com/"))
        self.assertIsNone(ydl.cookiejar.get_cookie_header("https://example.com/"))
        ydl.close()

    def test_bilibili_8k_quality_keeps_the_highest_stream_below_4320p(self) -> None:
        selected_format = bilibili_format_for_quality("4320p")

        self.assertIn("height<=4320", selected_format)

    def test_douyin_on_windows_does_not_read_a_locked_browser_database(self) -> None:
        url = "https://www.douyin.com/video/7651536731300236584"

        options = ydl_options("chrome", url=url)

        self.assertNotIn("cookiesfrombrowser", options)

    def test_douyin_ignores_a_stale_bilibili_login_selection(self) -> None:
        url = "https://www.douyin.com/video/7651536731300236584"

        options = ydl_options("bilibili", url=url)

        self.assertNotIn("cookiefile", options)
        self.assertNotIn("cookiesfrombrowser", options)

    def test_douyin_on_windows_uses_edge_before_the_standard_extractor(self) -> None:
        url = "https://www.douyin.com/video/7651536731300236584"

        class FakeYdl:
            def process_ie_result(self, info, download):
                return {**info, "processed": True, "download": download}

        with (
            patch("app.downloader.os.name", "nt"),
            patch(
                "app.downloader.extract_douyin_info",
                return_value={
                    "id": "7651536731300236584",
                    "formats": [{"url": "https://example.test/video.mp4"}],
                },
            ),
            patch("app.downloader.extract_info_with_retries") as standard_extract,
        ):
            result = extract_info_with_platform_fallback(FakeYdl(), url, download=False)

        self.assertTrue(result["processed"])
        self.assertFalse(result["download"])
        standard_extract.assert_not_called()

    def test_completed_mp4_is_preserved_when_ffprobe_is_unavailable(self) -> None:
        with patch("app.downloader.resolve_media_tool", return_value=None):
            self.assertTrue(is_playback_compatible_mp4(Path("video.mp4")))

    def test_windows_finds_ffmpeg_installed_by_winget(self) -> None:
        fake_tool = Path("C:/Users/test/AppData/Local/Microsoft/WinGet/Links/ffprobe.exe")
        with (
            patch("app.downloader.shutil.which", return_value=None),
            patch.dict(os.environ, {"LOCALAPPDATA": "C:/Users/test/AppData/Local"}),
            patch("app.downloader.Path.is_file", return_value=True),
        ):
            resolved = resolve_media_tool("ffprobe")

        self.assertEqual(Path(resolved), fake_tool)

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
