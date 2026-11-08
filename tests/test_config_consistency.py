# -*- coding: utf-8 -*-
"""指示09の受け入れ条件テスト: config.py と .env.example の設定値整合性"""
import os
import sys
import unittest
import ast

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
CODE_DIR = os.path.join(REPO_ROOT, "code")
BACKEND_DIR = os.path.join(CODE_DIR, "backend")


def parse_config_defaults(config_path):
    """AST解析で config.py 内の Settings クラスのデフォルト値を取得"""
    with open(config_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    defaults = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    key = item.target.id
                    val = ast.literal_eval(item.value)
                    defaults[key] = val
    return defaults


class TestConfigConsistency(unittest.TestCase):
    def test_env_example_matches_config_defaults(self):
        """.env.example の各設定値が config.py (Settings) のデフォルト値と完全に一致すること"""
        env_path = os.path.join(REPO_ROOT, ".env.example")
        config_path = os.path.join(BACKEND_DIR, "app", "config.py")

        self.assertTrue(os.path.exists(env_path), ".env.example が存在すること")
        self.assertTrue(os.path.exists(config_path), "config.py が存在すること")

        # .env.example の読み込み
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        env_dict = {}
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env_dict[k.strip()] = v.strip()

        # config.py の AST 解析
        config_defaults = parse_config_defaults(config_path)

        # 各重要設定値の突合
        self.assertEqual(float(env_dict["MIN_DELAY_SEC"]), config_defaults["min_delay_sec"])
        self.assertEqual(float(env_dict["MAX_DELAY_SEC"]), config_defaults["max_delay_sec"])
        self.assertEqual(int(env_dict["LONG_BREAK_EVERY"]), config_defaults["long_break_every"])
        self.assertEqual(float(env_dict["LONG_BREAK_SEC"]), config_defaults["long_break_sec"])
        self.assertEqual(int(env_dict["MAX_RETRIES"]), config_defaults["max_retries"])
        self.assertEqual(int(env_dict["MAX_QUERIES_PER_JOB"]), config_defaults["max_queries_per_job"])
        self.assertEqual(env_dict["SCRAPER_PROVIDER"], config_defaults["scraper_provider"])
        self.assertEqual(env_dict["HOST_API_TOKEN"], config_defaults["host_api_token"])


if __name__ == "__main__":
    unittest.main()
