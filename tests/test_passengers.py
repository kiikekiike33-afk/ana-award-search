# -*- coding: utf-8 -*-
"""指示02の受け入れ条件テスト: 搭乗人数の検索反映"""
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

from host_scraper_api import search_url
from app.scraper.ua import UAProvider


class TestPassengersPropagation(unittest.TestCase):
    def test_search_url_px_parameter(self):
        """search_url が passengers パラメータに応じて px=N を正しく構築すること"""
        url_1 = search_url("HND", "SFO", "2026-12-01", passengers=1)
        self.assertIn("px=1", url_1)

        url_2 = search_url("HND", "SFO", "2026-12-01", passengers=2)
        self.assertIn("px=2", url_2)

        url_4 = search_url("NRT", "HNL", "2026-12-15", passengers=4)
        self.assertIn("px=4", url_4)

    def test_uaprovider_propagates_passengers(self):
        """UAProvider.search が passengers=2 を host API 呼び出し URL に正しく付加すること"""
        provider = UAProvider()
        mock_response_data = {"status": "success", "flights": []}

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            provider.search({
                "origin": "HND",
                "destination": "SFO",
                "date": "2026-12-01",
                "passengers": 2,
                "cabin": "business",
            })

            # urlopen に渡された Request の URL を検証
            call_args = mock_urlopen.call_args
            req = call_args[0][0]
            self.assertIn("passengers=2", req.full_url)


if __name__ == "__main__":
    unittest.main()
