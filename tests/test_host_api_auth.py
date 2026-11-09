# -*- coding: utf-8 -*-
"""指示06および指示13の受け入れ条件テスト: ホストAPI認証トークンの検証とセキュリティ仕様"""
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

import host_scraper_api
from host_scraper_api import verify_token_middleware
from app.scraper.ua import UAProvider


class TestHostApiSecurity(unittest.TestCase):
    def test_unconfigured_token_rejected_with_503(self):
        """指示13要件: トークン未設定時はフェイルクローズとして 503 で拒否されること"""
        async def run_test():
            with patch.object(host_scraper_api, "HOST_API_TOKEN", ""), \
                 patch.object(host_scraper_api, "HOST_API_ALLOW_NO_TOKEN", False):

                mock_req = MagicMock()
                mock_req.url.path = "/api/search"
                mock_req.headers = {}
                mock_req.client.host = "127.0.0.1"

                mock_next = MagicMock()
                res = await verify_token_middleware(mock_req, mock_next)
                self.assertEqual(res.status_code, 503)
                mock_next.assert_not_called()

        asyncio.run(run_test())

    def test_allow_no_token_mode_allows_request(self):
        """指示13要件: HOST_API_ALLOW_NO_TOKEN=1 の場合は未設定でもアクセス許可されること"""
        async def run_test():
            with patch.object(host_scraper_api, "HOST_API_TOKEN", ""), \
                 patch.object(host_scraper_api, "HOST_API_ALLOW_NO_TOKEN", True):

                mock_req = MagicMock()
                mock_req.url.path = "/api/search"
                mock_req.headers = {}
                mock_req.client.host = "127.0.0.1"

                async def async_next(req):
                    return "ALLOWED"

                res = await verify_token_middleware(mock_req, async_next)
                self.assertEqual(res, "ALLOWED")

        asyncio.run(run_test())

    def test_leaked_old_token_rejected_with_503(self):
        """指示13要件: 公開済みの旧トークンが設定されている場合は安全のため 503 で拒否されること"""
        async def run_test():
            with patch.object(host_scraper_api, "HOST_API_TOKEN", "ana-award-local-token-2026"):

                mock_req = MagicMock()
                mock_req.url.path = "/api/search"
                mock_req.headers = {"X-Host-Token": "ana-award-local-token-2026"}
                mock_req.client.host = "127.0.0.1"

                mock_next = MagicMock()
                res = await verify_token_middleware(mock_req, mock_next)
                self.assertEqual(res.status_code, 503)
                mock_next.assert_not_called()

        asyncio.run(run_test())

    def test_authenticated_requests_with_valid_token(self):
        """有効なトークン設定時: 不正トークンは 401、正しいトークンは 200/通過となること"""
        async def run_test():
            test_token = "secure-random-token-test-1234567890abcdef"
            with patch.object(host_scraper_api, "HOST_API_TOKEN", test_token):

                # 1. トークンなし
                mock_req_no_token = MagicMock()
                mock_req_no_token.url.path = "/api/search"
                mock_req_no_token.headers = {}
                mock_req_no_token.client.host = "192.168.1.100"

                mock_next = MagicMock()
                res = await verify_token_middleware(mock_req_no_token, mock_next)
                self.assertEqual(res.status_code, 401)
                mock_next.assert_not_called()

                # 2. 不正トークン
                mock_req_invalid = MagicMock()
                mock_req_invalid.url.path = "/api/ana-autofill"
                mock_req_invalid.headers = {"X-Host-Token": "wrong-token"}
                mock_req_invalid.client.host = "192.168.1.100"

                mock_next.reset_mock()
                res_invalid = await verify_token_middleware(mock_req_invalid, mock_next)
                self.assertEqual(res_invalid.status_code, 401)
                mock_next.assert_not_called()

                # 3. 正しいトークン
                mock_req_valid = MagicMock()
                mock_req_valid.url.path = "/api/search"
                mock_req_valid.headers = {"X-Host-Token": test_token}
                mock_req_valid.client.host = "127.0.0.1"

                async def async_next(req):
                    return "OK"

                res_valid = await verify_token_middleware(mock_req_valid, async_next)
                self.assertEqual(res_valid, "OK")

        asyncio.run(run_test())

    def test_uaprovider_fails_when_token_not_configured(self):
        """指示13要件: バックエンドの UAProvider はトークン未設定時に明確なエラーを送出すること"""
        mock_settings = MagicMock()
        mock_settings.host_api_token = ""
        mock_settings.host_api_allow_no_token = False

        provider = UAProvider()
        with patch("app.scraper.ua._get_settings", return_value=mock_settings):
            with self.assertRaises(RuntimeError) as ctx:
                provider.search({
                    "origin": "HND",
                    "destination": "SFO",
                    "date": "2026-12-01",
                })
            self.assertIn("HOST_API_TOKEN が未設定です", str(ctx.exception))

    def test_uaprovider_fails_when_leaked_old_token_configured(self):
        """指示13要件: バックエンドの UAProvider は旧公開値が設定された場合に拒否すること"""
        mock_settings = MagicMock()
        mock_settings.host_api_token = "ana-award-local-token-2026"
        mock_settings.host_api_allow_no_token = False

        provider = UAProvider()
        with patch("app.scraper.ua._get_settings", return_value=mock_settings):
            with self.assertRaises(RuntimeError) as ctx:
                provider.search({
                    "origin": "HND",
                    "destination": "SFO",
                    "date": "2026-12-01",
                })
            self.assertIn("公開・漏洩した値が指定されています", str(ctx.exception))

    def test_uaprovider_sends_correct_token(self):
        """有効なトークン設定時: UAProvider がリクエストヘッダーに正しい X-Host-Token を付与すること"""
        test_token = "secure-random-token-test-1234567890abcdef"
        mock_settings = MagicMock()
        mock_settings.host_api_token = test_token
        mock_settings.host_api_allow_no_token = False

        provider = UAProvider()
        with patch("app.scraper.ua._get_settings", return_value=mock_settings), \
             patch("urllib.request.urlopen") as mock_urlopen:
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
            self.assertEqual(req.headers.get("X-host-token"), test_token)

    def test_no_hardcoded_leaked_token_as_default(self):
        """指示13要件: .env.example や設定ファイルのデフォルト値に旧固定値が残っていないこと"""
        env_example_path = os.path.join(REPO_ROOT, ".env.example")
        with open(env_example_path, "r", encoding="utf-8") as f:
            env_example_content = f.read()

        # .env.example の HOST_API_TOKEN 行が空文字であること
        for line in env_example_content.splitlines():
            if line.strip().startswith("HOST_API_TOKEN="):
                self.assertEqual(line.strip(), "HOST_API_TOKEN=")

        config_path = os.path.join(BACKEND_DIR, "app", "config.py")
        with open(config_path, "r", encoding="utf-8") as f:
            config_content = f.read()
        self.assertIn('host_api_token: str = ""', config_content)


if __name__ == "__main__":
    unittest.main()
