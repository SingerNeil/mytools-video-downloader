from __future__ import annotations

import os
import sys
from typing import Any

import yt_dlp
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from yt_dlp.extractor.tiktok import DouyinIE


DOUYIN_DETAIL_PATH = "/aweme/v1/web/aweme/detail/"
PAGE_TIMEOUT_MS = 60_000
DETAIL_WAIT_MS = 20_000


class DouyinBrowserError(RuntimeError):
    pass


def browser_channels() -> tuple[str, ...]:
    if os.name == "nt":
        # Edge is installed by default on supported Windows versions. Chrome is
        # a useful fallback without touching either browser's normal profile.
        return ("msedge", "chrome")
    if sys.platform == "darwin":
        return ("chrome", "msedge")
    return ("chrome", "msedge")


def _launch_browser(playwright: Any) -> tuple[Any, str]:
    errors: list[str] = []
    for channel in browser_channels():
        try:
            browser = playwright.chromium.launch(
                channel=channel,
                headless=True,
                args=["--autoplay-policy=no-user-gesture-required"],
            )
            return browser, channel
        except PlaywrightError as exc:
            errors.append(f"{channel}: {exc}")

    platform_hint = (
        "请确认 Microsoft Edge 可以正常启动。"
        if os.name == "nt"
        else "请安装 Google Chrome 或 Microsoft Edge。"
    )
    detail = "; ".join(errors)
    raise DouyinBrowserError(f"没有找到可用于抖音解析的浏览器。{platform_hint} {detail}".strip())


def fetch_douyin_detail(url: str) -> dict[str, Any]:
    captured: list[dict[str, Any]] = []

    try:
        with sync_playwright() as playwright:
            browser, _channel = _launch_browser(playwright)
            try:
                context = browser.new_context(
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                    viewport={"width": 1536, "height": 864},
                )
                try:
                    page = context.new_page()

                    def capture_detail(response: Any) -> None:
                        if DOUYIN_DETAIL_PATH not in response.url:
                            return
                        try:
                            payload = response.json()
                        except Exception:
                            return
                        detail = payload.get("aweme_detail") if isinstance(payload, dict) else None
                        if isinstance(detail, dict):
                            captured.append(detail)

                    page.on("response", capture_detail)
                    page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)

                    waited_ms = 0
                    while not captured and waited_ms < DETAIL_WAIT_MS:
                        page.wait_for_timeout(500)
                        waited_ms += 500
                finally:
                    context.close()
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        raise DouyinBrowserError("抖音页面加载超时，请检查网络后重试。") from exc
    except DouyinBrowserError:
        raise
    except PlaywrightError as exc:
        raise DouyinBrowserError(f"本机浏览器解析抖音页面失败：{exc}") from exc

    if not captured:
        raise DouyinBrowserError(
            "抖音页面没有返回视频信息，可能需要在浏览器中完成验证码，或该视频当前不可访问。"
        )
    return captured[-1]


def extract_douyin_info(url: str, ydl: yt_dlp.YoutubeDL) -> dict[str, Any]:
    detail = fetch_douyin_detail(url)
    try:
        info = DouyinIE(ydl)._parse_aweme_video_app(detail)
    except Exception as exc:
        raise DouyinBrowserError(f"无法解析浏览器返回的抖音视频信息：{exc}") from exc

    if not isinstance(info, dict) or not info.get("formats"):
        raise DouyinBrowserError("浏览器已打开抖音页面，但没有找到可下载的视频格式。")
    info["webpage_url"] = url
    info["original_url"] = url
    info["extractor"] = "Douyin (browser fallback)"
    info["extractor_key"] = "DouyinBrowser"
    return info
