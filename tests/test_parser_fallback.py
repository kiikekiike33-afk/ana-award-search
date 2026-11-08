# -*- coding: utf-8 -*-
"""指示04の受け入れ条件テスト: パーサ取りこぼし検知と無言脱落防止"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
CODE_DIR = os.path.join(REPO_ROOT, "code")
BACKEND_DIR = os.path.join(CODE_DIR, "backend")

sys.path.insert(0, CODE_DIR)
sys.path.insert(0, BACKEND_DIR)

sys.modules["pydantic_settings"] = MagicMock()
sys.modules["app.config"] = MagicMock()

from host_scraper_api import parse_flights, parse_flights_with_meta
from app.scraper.ua import UAProvider


class TestParserFallback(unittest.TestCase):
    def setUp(self):
        # 1. 括弧なし表記のカード
        # 2. パース不能カード（ゴミHTML）
        # 3. 説明文パース不能だがマイル・クラスありのカード
        self.html = """
        <html>
        <body>
          <!-- カード1: 括弧なし表記 Business | 88k | miles -->
          <div class="flight-card">
            <button aria-label="Details for the flight Depart Tokyo, JP (HND) at 11:35 PM and arrive Honolulu, HI, US (HNL) at 12:00 PM"></button>
            <div><div><div><div><div>
              <div>Flight 1</div>
              <div>Business | 88k | miles</div>
            </div></div></div></div></div>
          </div>

          <!-- カード2: パース不能カード（マイル情報などが一切取れない破損カード） -->
          <div class="flight-card">
            <button aria-label="Details for the flight Broken Card"></button>
            <div><div><div><div><div>
              <div>Something unparseable with no price or miles</div>
            </div></div></div></div></div>
          </div>

          <!-- カード3: 説明文の定型フォーマットに合わないが Business (I) があるカード -->
          <div class="flight-card">
            <button aria-label="Details for the flight NonStandard Description Without Depart and Arrive Format"></button>
            <div><div><div><div><div>
              <div>Flight 3</div>
              <div>Business (I) | 95k | miles</div>
            </div></div></div></div></div>
          </div>
        </body>
        </html>
        """

    def test_bracketless_miles_extracted(self):
        """括弧なし表記 (Business | 88k | miles) で business_miles が正しく取れること"""
        flights, failed_count = parse_flights_with_meta(self.html)
        self.assertEqual(flights[0]["business_miles"], "88k")
        self.assertEqual(flights[0]["business_fare_class"], "UNKNOWN")

    def test_parse_failed_count_reported(self):
        """パース不能カードが failed_count として計上され、無言で捨てられないこと"""
        flights, failed_count = parse_flights_with_meta(self.html)
        self.assertEqual(failed_count, 1)
        self.assertTrue(flights[1]["parse_failed"])

    def test_unparseable_description_not_dropped_in_direct_only(self):
        """説明文パース失敗便が direct_only=True でも無言で脱落せず、直行不明便として結果に残ること"""
        parsed_flights, failed_count = parse_flights_with_meta(self.html)
        mock_response_data = {
            "status": "success",
            "flights": parsed_flights,
            "parse_failed_count": failed_count,
        }

        provider = UAProvider()
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            # カード3 は Business (I) なので空席判定を通過する
            # direct_only=True で検索しても、カード3が無言脱落せず残ることを検証
            res = provider.search({
                "origin": "HND",
                "destination": "HNL",
                "date": "2026-12-01",
                "cabin": "business",
                "direct_only": True,
            })

            # カード3が結果に残っていること
            self.assertTrue(res.available)
            self.assertEqual(len(res.flights), 1)
            self.assertEqual(res.flights[0]["miles"], "95k")
            self.assertEqual(res.flights[0]["fare_class"], "I")
            # is_direct が None（直行/経由不明）となっていること
            self.assertIsNone(res.flights[0]["is_direct"])
            self.assertIn("直行/経由不明", res.flights[0]["stop_label"])

            # parse_failed_count が Availability に保持されていること
            self.assertEqual(res.parse_failed_count, 1)
            self.assertIn("パース失敗1件", res.seats_text)
            self.assertIn("直行不明1便", res.seats_text)


if __name__ == "__main__":
    unittest.main()
