"""広域エリア→空港コードへの展開と、検索条件（クエリ）の一覧づくり。"""
from datetime import date, timedelta

ORIGINS: dict[str, dict] = {
    "TYO": {"label": "東京（羽田・成田）", "airports": ["HND", "NRT"]},
    "HND": {"label": "東京（羽田）", "airports": ["HND"]},
    "NRT": {"label": "東京（成田）", "airports": ["NRT"]},
    "KIX": {"label": "大阪（関西）", "airports": ["KIX"]},
}

# ※就航地は変わるため、定期的に見直すこと
AREAS: dict[str, dict] = {
    "north_america": {"label": "北米・メキシコ", "airports": ["JFK", "ORD", "IAD", "IAH", "LAX", "SFO", "SEA", "SJC", "YVR", "YYZ", "MEX"]},
    "europe": {"label": "ヨーロッパ", "airports": ["LHR", "CDG", "FRA", "MUC", "BRU", "VIE", "MXP", "ARN", "IST"]},
    "southeast_asia": {"label": "東南アジア", "airports": ["BKK", "SIN", "KUL", "CGK", "MNL", "SGN", "HAN"]},
    "hawaii": {"label": "ハワイ", "airports": ["HNL"]},
}

# 空港コードと日本語都市名の対応表（画面表示用）
AIRPORT_NAMES: dict[str, str] = {
    "HND": "東京・羽田",
    "NRT": "東京・成田",
    "KIX": "大阪・関西",
    "JFK": "ニューヨーク",
    "ORD": "シカゴ",
    "IAD": "ワシントンD.C.",
    "IAH": "ヒューストン",
    "LAX": "ロサンゼルス",
    "SFO": "サンフランシスコ",
    "SEA": "シアトル",
    "SJC": "サンノゼ",
    "YVR": "バンクーバー",
    "YYZ": "トロント",
    "MEX": "メキシコシティ",
    "LHR": "ロンドン",
    "CDG": "パリ",
    "FRA": "フランクフルト",
    "MUC": "ミュンヘン",
    "BRU": "ブリュッセル",
    "VIE": "ウィーン",
    "MXP": "ミラノ",
    "ARN": "ストックホルム",
    "IST": "イスタンブール",
    "BKK": "バンコク",
    "SIN": "シンガポール",
    "KUL": "クアラルンプール",
    "CGK": "ジャカルタ",
    "MNL": "マニラ",
    "SGN": "ホーチミン",
    "HAN": "ハノイ",
    "HNL": "ホノルル",
}


def expand_origin(code: str) -> list[str]:
    """出発地コードを空港リストに展開する。"""
    return ORIGINS.get(code, {"airports": [code.upper()]})["airports"]


def expand_destination(key: str) -> list[str]:
    """エリア名なら空港の一覧に、3文字の空港コードならそのまま返す。"""
    if key in AREAS:
        return AREAS[key]["airports"]
    if len(key) == 3 and key.isalpha():
        return [key.upper()]
    raise ValueError(f"未対応の目的地です: {key}")


def daterange(start: date, end: date):
    """開始日から終了日まで1日ずつ返す。"""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


from .routes import get_valid_origins

def get_area_of_dest(dest: str) -> str:
    for area, data in AREAS.items():
        if dest in data["airports"]:
            return area
    return ""

def build_queries(p: dict) -> list[dict]:
    """日付を外側にしてループ → 早い日付の結果から順に画面に出る。"""
    start, end = date.fromisoformat(p["start_date"]), date.fromisoformat(p["end_date"])
    origins, dests = expand_origin(p["origin"]), expand_destination(p["destination"])
    queries = []
    direct_only = p.get("direct_only", True)

    for day in daterange(start, end):
        for d in dests:
            valid_os = get_valid_origins(get_area_of_dest(d), d) if direct_only else origins
            for o in origins:
                # 東京発の場合、直行便がない空港へのアクセスを省く
                if direct_only and o in ["HND", "NRT"] and o not in valid_os:
                    continue
                if o != d:
                    queries.append({
                        "origin": o, "destination": d, "date": day.isoformat(),
                        "cabin": p["cabin"], "passengers": p["passengers"],
                        "direct_only": direct_only,
                    })
    return queries
