# -*- coding: utf-8 -*-
"""指示12の受け入れ条件テスト: ANA自動入力の復路日付ロジック検証"""
import os
import sys
import unittest
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
CODE_DIR = os.path.join(REPO_ROOT, "code")

sys.path.insert(0, CODE_DIR)

from host_scraper_api import calculate_ana_return_date


class TestAnaReturnDate(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 11, 9)

    def test_normal_return_date(self):
        """通常時: 往路 + 7日となること"""
        dep = self.today + timedelta(days=30)
        ret = calculate_ana_return_date(dep, today=self.today)
        self.assertEqual(ret, dep + timedelta(days=7))

    def test_exact_limit_boundary(self):
        """上限ぴったり: 往路+7日 が上限日(今日+354日)にちょうど収まること"""
        dep = self.today + timedelta(days=347)
        ret = calculate_ana_return_date(dep, today=self.today)
        max_date = self.today + timedelta(days=354)
        self.assertEqual(ret, max_date)

    def test_exceeding_limit_clamped_to_max(self):
        """上限超過時: 往路+7日 が上限日を超える場合、上限日(今日+354日)に丸められること"""
        dep = self.today + timedelta(days=350)
        ret = calculate_ana_return_date(dep, today=self.today)
        max_date = self.today + timedelta(days=354)
        # 上限日(354日後)に丸められていること（+1日や同日にならない）
        self.assertEqual(ret, max_date)
        self.assertNotEqual(ret, dep)
        self.assertNotEqual(ret, dep + timedelta(days=1))

    def test_at_max_limit_clamped(self):
        """往路が上限日(今日+354日)自身の場合、上限日に丸められること"""
        dep = self.today + timedelta(days=354)
        ret = calculate_ana_return_date(dep, today=self.today)
        max_date = self.today + timedelta(days=354)
        self.assertEqual(ret, max_date)


if __name__ == "__main__":
    unittest.main()
