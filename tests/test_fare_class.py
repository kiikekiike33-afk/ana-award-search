# -*- coding: utf-8 -*-
"""指示01の受け入れ条件テスト: セーバー枠とダイナミックプライスの区別"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import json

# プロジェクトルートと各モジュールのパスを通す
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
CODE_DIR = os.path.join(REPO_ROOT, "code")
BACKEND_DIR = os.path.join(CODE_DIR, "backend")

sys.path.insert(0, CODE_DIR)
sys.path.insert(0, BACKEND_DIR)

# configの外部依存(pydantic_settings)をモック化
sys.modules["pydantic_settings"] = MagicMock()
sys.modules["app.config"] = MagicMock()

from host_scraper_api import parse_flights
from app.scraper.ua import UAProvider
from app.scraper.base import Availability


class TestFareClassFiltering(unittest.TestCase):
    def setUp(self):
        # サンプルHTMLフィクスチャの作成
        # 便1: Business (I) セーバー枠
        # 便2: Business (JN) ダイナミックプライス枠
        # 便3: 括弧なし Business クラス不明枠
        self.sample_html = """
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

          <div class="flight-card">
            <button aria-label="Details for the flight Depart Tokyo, JP (HND) at 05:00 PM and arrive San Francisco, CA, US (SFO) at 10:30 AM"></button>
            <div><div><div><div><div>
              <div>Flight 2</div>
              <div>Economy (HN) | 70k | miles</div>
              <div>Business (JN) | 320k | miles</div>
            </div></div></div></div></div>
          </div>

          <div class="flight-card">
            <button aria-label="Details for the flight Depart Tokyo, JP (NRT) at 06:00 PM and arrive Los Angeles, CA, US (LAX) at 12:00 PM"></button>
            <div><div><div><div><div>
              <div>Flight 3</div>
              <div>Business | 88k | miles</div>
            </div></div></div></div></div>
          </div>
        </body>
        </html>
        """

    def test_parse_flights_extracts_fare_class(self):
        """parse_flights が運賃クラス (I, JN, X) および UNKNOWN を正しく抽出できること"""
        flights = parse_flights(self.sample_html)
        self.assertEqual(len(flights), 3)

        # 便1: Business (I), Economy (X)
        self.assertEqual(flights[0]["business_miles"], "93.9k")
        self.assertEqual(flights[0]["business_fare_class"], "I")
        self.assertEqual(flights[0]["economy_miles"], "35k")
        self.assertEqual(flights[0]["economy_fare_class"], "X")

        # 便2: Business (JN), Economy (HN)
        self.assertEqual(flights[1]["business_miles"], "320k")
        self.assertEqual(flights[1]["business_fare_class"], "JN")

        # 便3: 括弧なし Business
        self.assertEqual(flights[2]["business_miles"], "88k")
        self.assertEqual(flights[2]["business_fare_class"], "UNKNOWN")

    def test_uaprovider_saver_vs_dynamic(self):
        """UAProvider が (I) のみを空席とし、(JN) をダイナミック枠として除外、UNKNOWN をクラス不明として除外すること"""
        parsed_flights = parse_flights(self.sample_html)
        mock_response_data = {"status": "success", "flights": parsed_flights}

        provider = UAProvider()

        # urllib.request.urlopen をモック化してローカルの parse 結果を注入
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            # ビジネス指定で検索（直行便・経由便の絞り込みなしで検証するため direct_only=False）
            res = provider.search({
                "origin": "HND",
                "destination": "HNL",
                "date": "2026-12-01",
                "cabin": "business",
                "direct_only": False,
            })

            # 検証1: 空席ありと判定されること
            self.assertTrue(res.available)

            # 検証2: 採用された便は (I) の1便のみであること
            self.assertEqual(len(res.flights), 1)
            self.assertEqual(res.flights[0]["fare_class"], "I")
            self.assertEqual(res.flights[0]["miles"], "93.9k")

            # 検証3: (JN) はダイナミック枠として1件除外されていること
            self.assertEqual(res.dynamic_count, 1)

            # 検証4: 括弧なし (UNKNOWN) はクラス不明として1件除外されていること（無言で混ぜない・無言で捨てない）
            self.assertEqual(res.unknown_count, 1)

            # 検証5: seats_text に除外情報が含まれていること
            self.assertIn("UAダイナミック枠1件除外", res.seats_text)
            self.assertIn("クラス不明1件除外", res.seats_text)

    def test_uaprovider_all_dynamic_results_in_no_seats(self):
        """ダイナミック枠 (JN) しか存在しない場合、空席なしとなり除外件数が seats_text に残ること"""
        parsed_flights = [
            {
                "flight_description": "Depart Tokyo, JP (HND) at 11:35 PM and arrive Honolulu, HI, US (HNL) at 12:00 PM",
                "business_miles": "320k",
                "business_fare_class": "JN",
                "economy_miles": "N/A",
                "economy_fare_class": None,
            }
        ]
        mock_response_data = {"status": "success", "flights": parsed_flights}

        provider = UAProvider()
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            res = provider.search({
                "origin": "HND",
                "destination": "HNL",
                "date": "2026-12-01",
                "cabin": "business",
                "direct_only": False,
            })

            # 空席なしになること
            self.assertFalse(res.available)
            self.assertEqual(len(res.flights), 0)
            self.assertEqual(res.dynamic_count, 1)
            self.assertIn("UAダイナミック枠1件除外", res.seats_text)


if __name__ == "__main__":
    unittest.main()
