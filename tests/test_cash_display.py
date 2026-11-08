# -*- coding: utf-8 -*-
"""指示03の受け入れ条件テスト: マイル表示保証・現金表示時のエラー検知伝搬"""
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

from host_scraper_api import check_display_mode
from app.scraper.ua import UAProvider
from app.scraper.base import CashDisplayError


class TestCashDisplayDetection(unittest.TestCase):
    def setUp(self):
        # 現金表示のサンプルHTML（$ や USD 表記で miles が一切ない）
        self.cash_html = """
        <html>
        <body>
          <div class="flight-card">
            <button aria-label="Details for the flight Depart Tokyo, JP (HND) at 11:35 PM and arrive Honolulu, HI, US (HNL) at 12:00 PM"></button>
            <div><div><div><div><div>
              <div>Flight 1</div>
              <div>Economy | $1,250</div>
              <div>Business | $4,800</div>
            </div></div></div></div></div>
          </div>
        </body>
        </html>
        """

        # マイル表示のサンプルHTML（miles 表記がある）
        self.miles_html = """
        <html>
        <body>
          <div class="flight-card">
            <button aria-label="Details for the flight Depart Tokyo, JP (HND) at 11:35 PM and arrive Honolulu, HI, US (HNL) at 12:00 PM"></button>
            <div><div><div><div><div>
              <div>Flight 1</div>
              <div>Economy (X) | 35k | miles</div>
              <div>Business (I) | 93.9k | miles</div>
            </div></div></div></div></div>
          </div>
        </body>
        </html>
        """

    def test_check_display_mode_cash_vs_miles(self):
        """check_display_mode が現金表示とマイル表示を正確に判定できること"""
        self.assertEqual(check_display_mode(self.cash_html), "cash")
        self.assertEqual(check_display_mode(self.miles_html), "miles")

    def test_uaprovider_raises_cash_display_error_on_409(self):
        """ホストAPIがHTTP 409を返した際、空席0件ではなくCashDisplayErrorが送出されること"""
        provider = UAProvider()

        with patch("urllib.request.urlopen") as mock_urlopen:
            # HTTP 409 エラーをシミュレート
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="http://host.docker.internal:8001/api/search",
                code=409,
                msg="Conflict: Cash Display Detected",
                hdrs={},
                fp=None,
            )

            with self.assertRaises(CashDisplayError) as ctx:
                provider.search({
                    "origin": "HND",
                    "destination": "SFO",
                    "date": "2026-12-01",
                    "cabin": "business",
                })

            self.assertIn("現金表示", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
