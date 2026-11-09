# -*- coding: utf-8 -*-
"""指示07の受け入れ条件テスト: We're sorry 一時制限時の扱いと README 整合性"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
CODE_DIR = os.path.join(REPO_ROOT, "code")
BACKEND_DIR = os.path.join(CODE_DIR, "backend")

sys.path.insert(0, CODE_DIR)
sys.path.insert(0, BACKEND_DIR)

sys.modules["pydantic_settings"] = MagicMock()
sys.modules["app.config"] = MagicMock()

from host_scraper_api import check_rate_limit
from app.scraper.ua import UAProvider
from app.scraper.base import RateLimitError


class TestRateLimitHandling(unittest.TestCase):
    def test_check_rate_limit(self):
        """check_rate_limit が We're sorry 画面を正確に判定できること"""
        sorry_html = "<html><body><div>We're sorry, but united.com was unable to complete your request. Please try again.</div></body></html>"
        normal_html = "<html><body><div>Details for the flight</div></body></html>"

        self.assertTrue(check_rate_limit(sorry_html))
        self.assertFalse(check_rate_limit(normal_html))

    def test_uaprovider_raises_rate_limit_error_on_429(self):
        """ホストAPIがHTTP 429を返した際、空席0件ではなくRateLimitErrorが送出されること"""
        provider = UAProvider()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="http://host.docker.internal:8001/api/search",
                code=429,
                msg="Too Many Requests: We're sorry",
                hdrs={},
                fp=None,
            )

            with self.assertRaises(RateLimitError) as ctx:
                provider.search({
                    "origin": "HND",
                    "destination": "SFO",
                    "date": "2026-12-01",
                    "cabin": "business",
                })

            self.assertIn("一時アクセス制限", str(ctx.exception))

    def test_readme_consistency(self):
        """docs/README.md の記述が実装実態と完全に一致していること（Cookie消去再構築の古い記述がないこと）"""
        readme_path = os.path.join(REPO_ROOT, "docs", "README.md")
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 古い誤った記述が含まれていないこと
        self.assertNotIn("自動でCookieを消去してブラウザセッションを再構築", content)

        # 実装の実態（Cookie消去は行わずセッション保護、一時制限検知時にスキップ・連続で自動停止）が書かれていること
        self.assertIn("Cookieの消去は行いません", content)
        self.assertIn("We're sorry", content)
        self.assertIn("自動停止", content)


if __name__ == "__main__":
    unittest.main()
