from __future__ import annotations

import unittest

import requests

from app.bilibili_auth import BilibiliAuthManager, NAV_URL, QR_GENERATE_URL, QR_POLL_URL


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.cookies = requests.cookies.RequestsCookieJar()
        self.closed = False
        self.poll_code = 0

    def get(self, url: str, **kwargs) -> FakeResponse:
        if url == QR_GENERATE_URL:
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "url": "https://passport.bilibili.com/login?qrcode_key=test",
                        "qrcode_key": "1234567890abcdef1234567890abcdef",
                    },
                }
            )
        if url == QR_POLL_URL:
            if self.poll_code == 0:
                self.cookies.set("SESSDATA", "secret-session", domain=".bilibili.com")
                self.cookies.set("bili_jct", "csrf-token", domain=".bilibili.com")
            return FakeResponse(
                {
                    "code": 0,
                    "data": {"code": self.poll_code, "message": "扫码状态"},
                }
            )
        if url == NAV_URL:
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "isLogin": True,
                        "uname": "测试用户",
                        "mid": 123,
                        "vipStatus": 1,
                    },
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    def close(self) -> None:
        self.closed = True


class BilibiliAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = FakeSession()
        self.manager = BilibiliAuthManager(session_factory=lambda: self.session)

    def test_qr_login_keeps_cookie_secret_out_of_public_status(self) -> None:
        qr = self.manager.start_qr_login()

        self.assertTrue(qr["image_data_url"].startswith("data:image/png;base64,"))
        result = self.manager.poll_qr_login(qr["qrcode_key"])

        self.assertEqual(result["state"], "authenticated")
        self.assertEqual(result["user"]["name"], "测试用户")
        self.assertTrue(result["user"]["vip"])
        self.assertNotIn("SESSDATA", str(self.manager.status()))
        cookie_data = self.manager.cookie_file().getvalue()
        self.assertIn(".bilibili.com\tTRUE", cookie_data)
        self.assertIn("SESSDATA\tsecret-session", cookie_data)
        self.assertTrue(self.session.closed)

    def test_qr_waiting_status_does_not_authenticate(self) -> None:
        self.session.poll_code = 86101
        qr = self.manager.start_qr_login()

        result = self.manager.poll_qr_login(qr["qrcode_key"])

        self.assertEqual(result["state"], "waiting")
        self.assertFalse(self.manager.status()["authenticated"])

    def test_logout_removes_in_memory_credentials(self) -> None:
        qr = self.manager.start_qr_login()
        self.manager.poll_qr_login(qr["qrcode_key"])

        status = self.manager.logout()

        self.assertFalse(status["authenticated"])
        self.assertIsNone(status["user"])


if __name__ == "__main__":
    unittest.main()
