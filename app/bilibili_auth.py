from __future__ import annotations

import base64
import io
import re
import time
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable

import qrcode
import requests


QR_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
QR_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}
QR_STATUS = {
    86101: ("waiting", "等待扫码"),
    86090: ("scanned", "已扫码，请在手机上确认"),
    86038: ("expired", "二维码已过期，请重新生成"),
    86083: ("expired", "二维码已失效，请重新生成"),
}


class BilibiliAuthError(RuntimeError):
    pass


@dataclass
class PendingLogin:
    session: requests.Session
    expires_at: float


class BilibiliAuthManager:
    def __init__(
        self,
        *,
        session_factory: Callable[[], requests.Session] = requests.Session,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._lock = RLock()
        self._pending: dict[str, PendingLogin] = {}
        self._cookies: dict[str, str] = {}
        self._user: dict[str, Any] | None = None

    def _cleanup_expired(self) -> None:
        now = self._clock()
        expired_keys = [key for key, login in self._pending.items() if login.expires_at <= now]
        for key in expired_keys:
            pending = self._pending.pop(key, None)
            if pending:
                pending.session.close()

    def start_qr_login(self) -> dict[str, Any]:
        session = self._session_factory()
        try:
            response = session.get(QR_GENERATE_URL, headers=REQUEST_HEADERS, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            session.close()
            raise BilibiliAuthError(f"生成 B 站登录二维码失败：{exc}") from exc

        if not isinstance(payload, dict):
            session.close()
            raise BilibiliAuthError("B 站没有返回有效的二维码响应。")
        data = payload.get("data")
        qr_url = data.get("url") if isinstance(data, dict) else None
        qr_key = data.get("qrcode_key") if isinstance(data, dict) else None
        if payload.get("code") != 0 or not isinstance(qr_url, str) or not isinstance(qr_key, str):
            session.close()
            raise BilibiliAuthError(payload.get("message") or "B 站没有返回有效的登录二维码。")
        if not QR_KEY_PATTERN.fullmatch(qr_key):
            session.close()
            raise BilibiliAuthError("B 站返回的二维码登录密钥格式无效。")

        image = qrcode.make(qr_url)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_data = base64.b64encode(buffer.getvalue()).decode("ascii")

        with self._lock:
            self._cleanup_expired()
            self._pending[qr_key] = PendingLogin(session=session, expires_at=self._clock() + 180)

        return {
            "qrcode_key": qr_key,
            "image_data_url": f"data:image/png;base64,{image_data}",
            "expires_in": 180,
        }

    def poll_qr_login(self, qr_key: str) -> dict[str, Any]:
        if not QR_KEY_PATTERN.fullmatch(qr_key):
            raise BilibiliAuthError("二维码登录密钥格式无效。")
        with self._lock:
            self._cleanup_expired()
            pending = self._pending.get(qr_key)
        if pending is None:
            return {"state": "expired", "message": "二维码已过期，请重新生成。"}

        try:
            response = pending.session.get(
                QR_POLL_URL,
                params={"qrcode_key": qr_key, "source": "main-fe-header"},
                headers=REQUEST_HEADERS,
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise BilibiliAuthError(f"检查 B 站扫码状态失败：{exc}") from exc

        if not isinstance(payload, dict):
            raise BilibiliAuthError("B 站没有返回有效的扫码状态。")
        data = payload.get("data")
        status_code = data.get("code") if isinstance(data, dict) else None
        if payload.get("code") != 0 or not isinstance(status_code, int):
            raise BilibiliAuthError(payload.get("message") or "B 站没有返回有效的扫码状态。")
        if status_code != 0:
            state, default_message = QR_STATUS.get(status_code, ("waiting", "等待扫码确认"))
            if state == "expired":
                with self._lock:
                    self._pending.pop(qr_key, None)
                pending.session.close()
            return {"state": state, "message": data.get("message") or default_message}

        cookies = pending.session.cookies.get_dict()
        if not cookies.get("SESSDATA"):
            with self._lock:
                self._pending.pop(qr_key, None)
            pending.session.close()
            raise BilibiliAuthError("扫码成功，但 B 站没有返回 SESSDATA 登录信息。")
        try:
            user = self._fetch_user(pending.session)
        except BilibiliAuthError:
            with self._lock:
                self._pending.pop(qr_key, None)
            pending.session.close()
            raise
        with self._lock:
            self._cookies = cookies
            self._user = user
            self._pending.pop(qr_key, None)
        pending.session.close()
        return {"state": "authenticated", "message": "B 站登录成功", "user": user}

    def _fetch_user(self, session: requests.Session) -> dict[str, Any]:
        try:
            response = session.get(NAV_URL, headers=REQUEST_HEADERS, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise BilibiliAuthError(f"验证 B 站登录状态失败：{exc}") from exc

        if not isinstance(payload, dict):
            raise BilibiliAuthError("B 站没有返回有效的用户信息。")
        data = payload.get("data")
        if payload.get("code") != 0 or not isinstance(data, dict) or not data.get("isLogin"):
            raise BilibiliAuthError("B 站登录状态验证失败，请重新扫码。")
        return {
            "name": data.get("uname") or "已登录用户",
            "mid": data.get("mid"),
            "vip": bool(data.get("vipStatus")),
        }

    def cookie_file(self) -> io.StringIO:
        with self._lock:
            if not self._cookies:
                raise BilibiliAuthError("尚未扫码登录 B 站，请先在页面完成扫码登录。")
            lines = ["# Netscape HTTP Cookie File\n"]
            for name, value in self._cookies.items():
                if any(character in name or character in value for character in "\t\r\n"):
                    raise BilibiliAuthError("B 站返回了无效的 Cookie 登录信息，请重新扫码。")
                lines.append(f".bilibili.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}\n")
            return io.StringIO("".join(lines))

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"authenticated": bool(self._cookies), "user": self._user}

    def logout(self) -> dict[str, Any]:
        with self._lock:
            for pending in self._pending.values():
                pending.session.close()
            self._cookies.clear()
            self._user = None
            self._pending.clear()
        return self.status()


bilibili_auth = BilibiliAuthManager()
