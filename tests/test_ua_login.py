# -*- coding: utf-8 -*-
"""指示08の受け入れ条件テスト: UAログイン時のユーザー名自動入力"""
import os
import sys
import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
CODE_DIR = os.path.join(REPO_ROOT, "code")

sys.path.insert(0, CODE_DIR)

from host_scraper_api import fill_login_credentials


class TestUALogin(unittest.TestCase):
    def test_fill_login_credentials_both_fields(self):
        """ユーザー名欄とパスワード欄の両方がある画面で、両方が自動入力されること"""
        async def run_test():
            mock_page = MagicMock()
            mock_page.get_by_role.return_value = MagicMock(count=AsyncMock(return_value=0))

            user_locator = MagicMock()
            user_locator.count = AsyncMock(return_value=1)
            user_locator.first.is_visible = AsyncMock(return_value=True)
            user_locator.first.fill = AsyncMock()

            pw_locator = MagicMock()
            pw_locator.count = AsyncMock(return_value=1)
            pw_locator.first.is_visible = AsyncMock(return_value=True)
            pw_locator.first.fill = AsyncMock()

            submit_locator = MagicMock()
            submit_locator.count = AsyncMock(return_value=1)
            submit_locator.first.is_visible = AsyncMock(return_value=True)
            submit_locator.first.click = AsyncMock()

            def mock_locator_call(sel, **kwargs):
                if "password" in sel:
                    return pw_locator
                if "submit" in sel or "Sign in" in sel or "button" in sel:
                    return submit_locator
                return user_locator

            mock_page.locator.side_effect = mock_locator_call

            with patch("asyncio.sleep", AsyncMock()):
                entered = await fill_login_credentials(mock_page, "MP123456", "SecretPass123")

            self.assertTrue(entered)
            user_locator.first.fill.assert_called_once_with("MP123456")
            pw_locator.first.fill.assert_called_once_with("SecretPass123")
            submit_locator.first.click.assert_called_once()

        asyncio.run(run_test())

    def test_fill_login_credentials_step_based(self):
        """ユーザー名欄のみが表示されているステップ型画面で、ユーザー名が入力されて次へが押されること"""
        async def run_test():
            mock_page = MagicMock()
            mock_page.get_by_role.return_value = MagicMock(count=AsyncMock(return_value=0))

            user_locator = MagicMock()
            user_locator.count = AsyncMock(return_value=1)
            user_locator.first.is_visible = AsyncMock(return_value=True)
            user_locator.first.fill = AsyncMock()

            pw_locator = MagicMock()
            pw_locator.count = AsyncMock(return_value=0)
            pw_locator.first.is_visible = AsyncMock(return_value=False)

            next_locator = MagicMock()
            next_locator.count = AsyncMock(return_value=1)
            next_locator.first.is_visible = AsyncMock(return_value=True)
            next_locator.first.click = AsyncMock()

            def mock_locator_call(sel, **kwargs):
                if "password" in sel:
                    return pw_locator
                if "Continue" in sel or "Next" in sel:
                    return next_locator
                return user_locator

            mock_page.locator.side_effect = mock_locator_call

            with patch("asyncio.sleep", AsyncMock()):
                entered = await fill_login_credentials(mock_page, "test@example.com", "SecretPass123")

            self.assertTrue(entered)
            user_locator.first.fill.assert_called_once_with("test@example.com")
            next_locator.first.click.assert_called_once()

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
