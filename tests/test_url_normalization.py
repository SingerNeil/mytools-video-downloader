from __future__ import annotations

import unittest

from app.downloader import extract_first_url, format_for_url, validate_url


DOUYIN_VIDEO_URL = "https://www.douyin.com/video/7650469260520087209"


class UrlNormalizationTests(unittest.TestCase):
    def test_douyin_self_modal_html_entities_becomes_video_url(self) -> None:
        url = (
            "https://www.douyin.com/user/self?from_tab_name=main"
            "&amp;modal_id=7650469260520087209&amp;showTab=like"
        )

        self.assertEqual(validate_url(url), DOUYIN_VIDEO_URL)

    def test_douyin_self_modal_plain_query_becomes_video_url(self) -> None:
        url = (
            "https://www.douyin.com/user/self?from_tab_name=main"
            "&modal_id=7650469260520087209&showTab=like"
        )

        self.assertEqual(validate_url(url), DOUYIN_VIDEO_URL)

    def test_douyin_share_text_extracts_and_normalizes_url(self) -> None:
        share_text = (
            "复制打开抖音，看看这个视频 "
            "https://www.douyin.com/user/self?modal_id=7650469260520087209 "
            "更多内容"
        )

        self.assertEqual(validate_url(share_text), DOUYIN_VIDEO_URL)

    def test_direct_douyin_video_url_is_unchanged(self) -> None:
        self.assertEqual(validate_url(DOUYIN_VIDEO_URL), DOUYIN_VIDEO_URL)

    def test_extract_first_url_decodes_html_entities(self) -> None:
        value = "链接：https://example.com/watch?a=1&amp;b=2"

        self.assertEqual(extract_first_url(value), "https://example.com/watch?a=1&b=2")

    def test_unrelated_url_is_unchanged(self) -> None:
        url = "https://www.bilibili.com/video/BV1xx?p=2"

        self.assertEqual(validate_url(url), url)

    def test_douyin_best_prefers_native_h264(self) -> None:
        self.assertEqual(
            format_for_url("best", DOUYIN_VIDEO_URL),
            "b[vcodec^=h264]/b[vcodec^=avc1]/b",
        )

    def test_douyin_720p_handles_portrait_dimensions(self) -> None:
        selector = format_for_url("720p", DOUYIN_VIDEO_URL)

        self.assertIn("[width<=1280][height<=1280][vcodec^=h264]", selector)


if __name__ == "__main__":
    unittest.main()
