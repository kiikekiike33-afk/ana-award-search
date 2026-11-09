# -*- coding: utf-8 -*-
"""指示11の受け入れ条件テスト: リポジトリ単体起動の整備と依存関係固定の検証"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
CODE_DIR = os.path.join(REPO_ROOT, "code")
BACKEND_DIR = os.path.join(CODE_DIR, "backend")

sys.path.insert(0, CODE_DIR)
sys.path.insert(0, BACKEND_DIR)

from unittest.mock import MagicMock
sys.modules["pydantic_settings"] = MagicMock()
sys.modules["app.config"] = MagicMock()

from host_scraper_api import load_app_env
from app.scraper.mock import MockProvider


class TestStandaloneReadiness(unittest.TestCase):
    def test_dockerfile_excludes_playwright_chromium(self):
        """backend/Dockerfile に不要な playwright install chromium が含まれていないこと"""
        dockerfile_path = os.path.join(BACKEND_DIR, "Dockerfile")
        with open(dockerfile_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("playwright install", content)
        self.assertNotIn("chromium", content)
        self.assertIn("pip install --no-cache-dir -r requirements.txt", content)

    def test_requirements_versioned_and_no_playwright(self):
        """backend/requirements.txt にバージョン制約が付与され、playwright が除外されていること"""
        req_path = os.path.join(BACKEND_DIR, "requirements.txt")
        with open(req_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        for line in lines:
            self.assertTrue(any(op in line for op in [">=", "==", "<="]), f"{line} にバージョン制約があること")
            self.assertFalse(line.startswith("playwright"), "backend に playwright が含まれないこと")

    def test_docker_compose_has_fallback_env(self):
        """docker-compose.yml の env_file がクローン直後でも起動可能な多段階フォールバックであること"""
        compose_path = os.path.join(CODE_DIR, "docker-compose.yml")
        with open(compose_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("required: false", content)
        self.assertIn(".env.example", content)

    def test_load_app_env_finds_env(self):
        """load_app_env が環境設定ファイルを正常に発見・読み込めること"""
        loaded = load_app_env()
        self.assertIsNotNone(loaded)
        self.assertTrue(os.path.exists(loaded))

    def test_mock_provider_works_without_credentials(self):
        """MockProvider が認証情報なしで独立して検索結果を返せること"""
        provider = MockProvider()
        res = provider.search({
            "origin": "HND",
            "destination": "SFO",
            "date": "2026-12-01",
            "cabin": "business",
        })
        self.assertIsNotNone(res)
        self.assertTrue(hasattr(res, "available"))
        self.assertTrue(hasattr(res, "flights"))


if __name__ == "__main__":
    unittest.main()
