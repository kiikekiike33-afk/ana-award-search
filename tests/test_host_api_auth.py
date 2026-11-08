# -*- coding: utf-8 -*-
"""指示06の受け入れ条件テスト: ホストAPI認証トークンの検証"""
import os
import sys
import unittest
import asyncio
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
CODE_DIR = os.path.join(REPO_ROOT, "code")
BACKEND_DIR = os.path.join(CODE_DIR, "backend")

sys.path.insert(0, CODE_DIR)
sys.path.insert(0, BACKEND_DIR)

sys.modules["pydantic_settings"] = MagicMock()
sys.modules["app.config"] = MagicMock()

from host_scraper_api import verify_token_middleware, HOST_API_TOKEN
from app.scraper.ua import UAProvider


class TestHostApiSecurity(unittest.TestCase):
    def test_unauthenticated_request_rejected(self):
        """トークンなしおよび不正トークンのリクエストが401で拒否されること"""
        async def run_test():
            # 1. トークンなしのリクエスト
            mock_req_no_token = MagicMock()
            mock_req_no_token.url.path = "/api/search"
            mock_req_no_token.headers = {}
            mock_req_no_token.client.host = "192.168.1.100"

            mock_next = MagicMock()
            res = await verify_token_middleware(mock_req_no_token, mock_next)
            self.assertEqual(res.status_code, 401)
            mock_next.assert_not_called()

            # 2. 不正なトークンのリクエスト
            mock_req_invalid = MagicMock()
            mock_req_invalid.url.path = "/api/ana-autofill"
            mock_req_invalid.headers = {"X-Host-Token": "attacker-token"}
            mock_req_invalid.client.host = "192.168.1.100"

            mock_next.reset_mock()
            res_invalid = await verify_token_middleware(mock_req_invalid, mock_next)
            self.assertEqual(res_invalid.status_code, 401)
            mock_next.assert_not_called()

            # 3. 正しいトークンのリクエスト
            mock_req_valid = MagicMock()
            mock_req_valid.url.path = "/api/search"
            mock_req_valid.headers = {"X-Host-Token": HOST_API_TOKEN}
            mock_req_valid.client.host = "127.0.0.1"

            mock_next_valid = MagicMock()
            async def async_next(req):
                return "OK"
            res_valid = await verify_token_middleware(mock_req_valid, async_next)
            self.assertEqual(res_valid, "OK")

        asyncio.run(run_test())

    def test_uaprovider_sends_correct_token(self):
        """UAProvider がリクエストヘッダーに正しい X-Host-Token を付与していること"""
        sys.modules["app.config"].settings.host_api_token = HOST_API_TOKEN
        provider = UAProvider()
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"status": "success", "flights": []}'
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            provider.search({
                "origin": "HND",
                "destination": "SFO",
                "date": "2026-12-01",
                "cabin": "business",
            })

            req = mock_urlopen.call_args[0][0]
            self.assertEqual(req.headers.get("X-host-token"), HOST_API_TOKEN)


if __name__ == "__main__":
    unittest.main()
