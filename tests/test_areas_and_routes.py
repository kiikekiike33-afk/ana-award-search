# -*- coding: utf-8 -*-
"""指示05の受け入れ条件テスト: エリア追加と直行路線の検証"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
CODE_DIR = os.path.join(REPO_ROOT, "code")
BACKEND_DIR = os.path.join(CODE_DIR, "backend")

sys.path.insert(0, CODE_DIR)
sys.path.insert(0, BACKEND_DIR)

from app.areas import build_queries, AREAS, AIRPORT_NAMES
from app.routes import DIRECT_FLIGHTS, get_valid_origins


class TestAreasAndRoutes(unittest.TestCase):
    def test_oceania_queries(self):
        """オセアニアエリアの検索クエリ生成と直行便出発地の検証"""
        self.assertIn("oceania", AREAS)
        self.assertEqual(AREAS["oceania"]["airports"], ["SYD", "PER", "MEL"])

        # direct_only=True で東京(TYO)発の場合
        queries = build_queries({
            "origin": "TYO",
            "destination": "oceania",
            "start_date": "2026-12-01",
            "end_date": "2026-12-01",
            "cabin": "business",
            "passengers": 1,
            "direct_only": True,
        })

        # SYD は HND 直行便のみ
        syd_queries = [q for q in queries if q["destination"] == "SYD"]
        self.assertEqual(len(syd_queries), 1)
        self.assertEqual(syd_queries[0]["origin"], "HND")

        # PER は NRT 直行便のみ
        per_queries = [q for q in queries if q["destination"] == "PER"]
        self.assertEqual(len(per_queries), 1)
        self.assertEqual(per_queries[0]["origin"], "NRT")

        # MEL は直行便がないため direct_only では生成されない
        mel_queries = [q for q in queries if q["destination"] == "MEL"]
        self.assertEqual(len(mel_queries), 0)

    def test_india_queries(self):
        """インドアリアの検索クエリ生成と直行便出発地の検証"""
        self.assertIn("india", AREAS)
        self.assertEqual(AREAS["india"]["airports"], ["DEL", "BOM"])

        queries = build_queries({
            "origin": "TYO",
            "destination": "india",
            "start_date": "2026-12-01",
            "end_date": "2026-12-01",
            "cabin": "economy",
            "passengers": 1,
            "direct_only": True,
        })

        # DEL は HND 直行
        del_queries = [q for q in queries if q["destination"] == "DEL"]
        self.assertEqual(len(del_queries), 1)
        self.assertEqual(del_queries[0]["origin"], "HND")

        # BOM は NRT 直行
        bom_queries = [q for q in queries if q["destination"] == "BOM"]
        self.assertEqual(len(bom_queries), 1)
        self.assertEqual(bom_queries[0]["origin"], "NRT")

    def test_europe_waw_zrh(self):
        """欧州エリアに WAW, ZRH が追加され、成田発着となることの検証"""
        self.assertIn("WAW", AREAS["europe"]["airports"])
        self.assertIn("ZRH", AREAS["europe"]["airports"])

        queries = build_queries({
            "origin": "TYO",
            "destination": "europe",
            "start_date": "2026-12-01",
            "end_date": "2026-12-01",
            "cabin": "business",
            "passengers": 1,
            "direct_only": True,
        })

        waw_queries = [q for q in queries if q["destination"] == "WAW"]
        self.assertEqual(len(waw_queries), 1)
        self.assertEqual(waw_queries[0]["origin"], "NRT")

        zrh_queries = [q for q in queries if q["destination"] == "ZRH"]
        self.assertEqual(len(zrh_queries), 1)
        self.assertEqual(zrh_queries[0]["origin"], "NRT")

    def test_airport_names_defined(self):
        """追加空港の日本語名が定義されていること"""
        for code in ["SYD", "PER", "MEL", "DEL", "BOM", "WAW", "ZRH"]:
            self.assertIn(code, AIRPORT_NAMES)
            self.assertTrue(len(AIRPORT_NAMES[code]) > 0)


if __name__ == "__main__":
    unittest.main()
