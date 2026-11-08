# -*- coding: utf-8 -*-
"""指示10の受け入れ条件テスト: .gitignore のセキュリティ除外検証"""
import os
import subprocess
import unittest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
GIT_EXE = r"C:\Program Files\Git\cmd\git.exe"


class TestGitignore(unittest.TestCase):
    def test_security_patterns_ignored(self):
        """セッション情報・Cookie・DB・envバックアップが正しく除外されること"""
        test_files = [
            "storage_state.json",
            "storage_state_user.json",
            "ana_storage_state.json",
            "network.har",
            "app.db",
            "session.sqlite",
            "session.sqlite3",
            "cookies.txt",
            "cookies_user.json",
            ".env.bak",
            ".env.save",
            ".env.backup",
            ".env.local",
        ]

        cmd = [GIT_EXE, "-C", REPO_ROOT, "check-ignore"] + test_files
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        ignored_files = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]

        for f in test_files:
            self.assertIn(f, ignored_files, f"{f} が .gitignore で除外されていること")

    def test_env_example_not_ignored(self):
        """.env.example は除外されずGit追跡可能であること"""
        cmd = [GIT_EXE, "-C", REPO_ROOT, "check-ignore", ".env.example"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # git check-ignore はマッチしない場合 exit code 1 を返す
        self.assertNotEqual(res.returncode, 0)
        self.assertNotIn(".env.example", res.stdout)


if __name__ == "__main__":
    unittest.main()
