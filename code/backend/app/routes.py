# -*- coding: utf-8 -*-
"""直行便の就航路線（2026年時点の確認済み運航情報）
存在しない組み合わせ（例：NRT-LHRなど）を省くための定義
"""
DIRECT_FLIGHTS = {
    "europe": {
        "LHR": ["HND"],
        "CDG": ["HND"],
        "FRA": ["HND"],
        "MUC": ["HND"],
        "BRU": ["NRT"],
        "VIE": ["HND"],
        "MXP": ["HND"],
        "ARN": ["HND"],
        "IST": ["HND"],
        "WAW": ["NRT"],  # LOTポーランド航空 成田直行便
        "ZRH": ["NRT"],  # スイスインターナショナルエアラインズ 成田直行便
    },
    "north_america": {
        "JFK": ["HND"],
        "ORD": ["HND", "NRT"],
        "IAD": ["HND"],
        "IAH": ["HND"],
        "LAX": ["HND", "NRT"],
        "SFO": ["HND", "NRT"],
        "SEA": ["HND"],
        "SJC": ["NRT"],
        "YVR": ["HND", "NRT"],
        "YYZ": ["HND"],
        "MEX": ["NRT"],
    },
    "southeast_asia": {
        "BKK": ["HND", "NRT"],
        "SIN": ["HND", "NRT"],
        "KUL": ["HND", "NRT"],
        "CGK": ["HND", "NRT"],
        "MNL": ["HND", "NRT"],
        "SGN": ["HND", "NRT"],
        "HAN": ["NRT"],
    },
    "oceania": {
        "SYD": ["HND"],  # ANA 羽田直行便
        "PER": ["NRT"],  # ANA 成田直行便
        "MEL": [],       # ANA/スターアライアンス直行便なし（経由便のみ。direct_only時に省く）
    },
    "india": {
        "DEL": ["HND"],  # ANA / エア・インディア 羽田直行便
        "BOM": ["NRT"],  # ANA 成田直行便
    },
    "hawaii": {
        "HNL": ["HND", "NRT"],
    }
}

def get_valid_origins(area: str, dest: str) -> list[str]:
    """指定エリア・目的地の直行便出発地（TYO）を返す"""
    if area in DIRECT_FLIGHTS and dest in DIRECT_FLIGHTS[area]:
        return DIRECT_FLIGHTS[area][dest]
    return ["HND", "NRT"]  # 未定義のものは両方検索
