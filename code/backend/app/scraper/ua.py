"""ユナイテッド航空（UA）の検索APIを経由してスターアライアンス特典枠を取得するプロバイダ"""
import json
import re
import urllib.error
import urllib.request
from .base import AwardProvider, Availability, BlockedError, CashDisplayError, RateLimitError, RetryableError

try:
    from ..config import settings
except Exception:
    settings = None


def _parse_miles_num(miles_str: str) -> float:
    """'55k' や '93.9k' などの文字列からソート用の数値（55.0など）を取り出す"""
    m = re.search(r"([\d\.]+)", str(miles_str))
    return float(m.group(1)) if m else 9999.0


def _extract_stop_codes(stops_text: str) -> str:
    """'Seoul, KR (ICN)' などの経由地テキストから空港コード（ICN等）を抽出する"""
    if not stops_text:
        return ""
    codes = re.findall(r"\(([A-Z]{3})\)", stops_text)
    if codes:
        return "・".join(codes) + "経由"
    return stops_text.strip() + "経由"


class UAProvider(AwardProvider):
    """Windowsホスト側で稼働するPlaywright APIサーバーを呼び出すプロバイダ"""

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def relogin(self) -> None:
        pass

    def search(self, query: dict) -> Availability:
        origin = query.get("origin", "")
        dest = query.get("destination", "")
        date_str = query.get("date", "")
        passengers = query.get("passengers", 1)

        # Dockerコンテナの中から、Windowsホスト（host.docker.internal）の8001番ポートへ通信
        url = f"http://host.docker.internal:8001/api/search?origin={origin}&destination={dest}&date={date_str}&passengers={passengers}"

        try:
            # ブラウザの自動操作（ログイン時の確認コード手打ち待機を含む）が終わるまで最長360秒（6分）待機
            raw_token = getattr(settings, "host_api_token", None) if settings else None
            token = raw_token if isinstance(raw_token, str) else "ana-award-local-token-2026"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "AnaAwardSearchWorker/1.0",
                    "X-Host-Token": token,
                },
            )
            with urllib.request.urlopen(req, timeout=360) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass

            if e.code == 401:
                if "トークン" in err_body or "token" in err_body.lower():
                    raise RetryableError(f"ホストAPI認証エラー: 共有トークンが不正です ({err_body})")
                # 認証コード待ちタイムアウト時はリトライや次の都市への移動を一切行わず、その場で検索ジョブ全体を停止する
                raise BlockedError("認証コード入力待ちのため検索を一時停止しました（再度のログイン試行は行いません）。Chrome画面でコードを入力してログイン完了後、もう一度検索を開始してください。")
            if e.code == 409:
                # 現金表示エラー（空席なしと誤認させず、エラーとして伝搬）
                raise CashDisplayError("ユナイテッド航空の検索結果が現金表示になっているため、マイル特典枠を読み取れませんでした。マイル表示への切替が必要です。")
            if e.code == 429:
                # We're sorry 一時制限画面エラー（空席なしと誤認させず、制限エラーとして伝搬）
                raise RateLimitError("ユナイテッド航空の一時アクセス制限（We're sorry画面）を検知しました。")
            raise RetryableError(f"Windows側のAPIサーバーとの通信に失敗しました: {e}")
        except Exception as e:
            raise RetryableError(f"Windows側のAPIサーバーとの通信に失敗しました: {e}")

        raw_flights = data.get("flights", [])
        cabin = query.get("cabin", "economy")
        direct_only = query.get("direct_only", True)

        # スターアライアンス提携社（ANA等）特典枠として発券可能なセーバー運賃クラス
        # エコノミー: X, ビジネス: I, ファースト: O (ファースト指定時は I または O を許容)
        # ※JN, IN, ZN, YN, HN 等はUA自社会員向け専用またはダイナミックプライス枠のため除外
        SAVER_CLASSES = {
            "economy": {"X"},
            "business": {"I"},
            "first": {"O", "I"},
        }
        target_allowed_classes = SAVER_CLASSES.get(cabin, {"X", "I", "O"})

        formatted_flights = []
        dynamic_flights = []
        unknown_class_flights = []

        for f in raw_flights:
            eco = f.get("economy_miles", "N/A")
            bus = f.get("business_miles", "N/A")
            first = f.get("first_miles", "N/A")
            eco_cls = f.get("economy_fare_class")
            bus_cls = f.get("business_fare_class")
            first_cls = f.get("first_fare_class")
            desc = f.get("flight_description", "")

            # 検索条件のクラスに応じたマイル数と運賃クラスを取得
            if cabin == "economy":
                target_miles = eco
                target_class = eco_cls
            elif cabin == "business":
                target_miles = bus
                target_class = bus_cls
            else: # first
                if first != "N/A" and first:
                    target_miles = first
                    target_class = first_cls
                else:
                    target_miles = bus
                    target_class = bus_cls

            # 「55k」などの数字が含まれていない場合（N/Aなど）は空席なしとみなしてスキップ
            if not re.search(r"\d", str(target_miles)):
                continue

            # 運賃クラスの検証（ダイナミック枠およびクラス不明枠の除外）
            if not target_class or target_class == "UNKNOWN":
                # クラス不明便（無言で空席に混ぜず、無言で捨てずカウント）
                unknown_class_flights.append(f)
                continue

            if target_class not in target_allowed_classes:
                # UA自社ダイナミック枠等（ANA発券対象外）として除外
                dynamic_flights.append(f)
                continue

            miles_num = _parse_miles_num(target_miles)

            # 文章から「出発空港」「出発時刻」「到着空港」「到着時刻」「経由地」を抽出する
            # 例: Depart Tokyo, JP (HND) at 11:35 PM and arrive Honolulu, HI, US (HNL) at 6:30 PM with stops at Guam...
            m = re.search(
                r"Depart .*?\((.*?)\) at (.*?)\s+and arrive .*?\((.*?)\) at (.*?)(?:\s+with stops? at (.*))?$",
                desc.strip(),
            )
            if m:
                orig_code, dep_time, dest_code, arr_time, stops_raw = m.groups()
                is_direct = not bool(stops_raw and stops_raw.strip()) and ("stop" not in desc.lower())
                stop_label = "直行便" if is_direct else _extract_stop_codes(stops_raw)
                flight_no = f"💺 {target_miles} ({dep_time} → {arr_time} [{stop_label}])"
            else:
                orig_code, dep_time, dest_code, arr_time = origin, "", dest, ""
                is_direct = None # 直行/経由の判定不能（指示04対応: 偽陰性を防ぐためNoneとして保持）
                stop_label = "直行/経由不明（要詳細確認）"
                flight_no = f"💺 {target_miles} (詳細確認)"

            # 「直行便のみ」が有効な場合:
            # 経由便と確定しているもの（is_direct is False）のみ除外し、直行不明便（is_direct is None）は無言で捨てない
            if direct_only:
                if is_direct is False:
                    continue
                if orig_code != origin or dest_code != dest:
                    continue

            formatted_flights.append({
                "flight_no": flight_no,
                "miles": target_miles,
                "miles_num": miles_num,
                "fare_class": target_class,
                "economy_miles": eco,
                "economy_fare_class": eco_cls,
                "business_miles": bus,
                "business_fare_class": bus_cls,
                "orig_code": orig_code,
                "dest_code": dest_code,
                "dep_time": dep_time,
                "arr_time": arr_time,
                "is_direct": is_direct,
                "stop_label": stop_label,
            })

        # 見やすいように「直行便(0)」→「直行不明(1)」→「経由便(2)」→「必要マイルが少ない順」に並び替える
        def _sort_priority(x):
            if x["is_direct"] is True:
                return 0
            if x["is_direct"] is None:
                return 1
            return 2

        formatted_flights.sort(key=lambda x: (_sort_priority(x), x["miles_num"]))

        available = len(formatted_flights) > 0
        direct_count = sum(1 for x in formatted_flights if x["is_direct"] is True)
        unknown_direct_count = sum(1 for x in formatted_flights if x["is_direct"] is None)
        dynamic_count = len(dynamic_flights)
        unknown_count = len(unknown_class_flights)
        parse_failed_count = data.get("parse_failed_count", 0)

        notes = []
        if dynamic_count > 0:
            notes.append(f"UAダイナミック枠{dynamic_count}件除外")
        if unknown_count > 0:
            notes.append(f"クラス不明{unknown_count}件除外")
        if parse_failed_count > 0:
            notes.append(f"パース失敗{parse_failed_count}件")
        if unknown_direct_count > 0:
            notes.append(f"直行不明{unknown_direct_count}便")
        note_str = f" （{', '.join(notes)}）" if notes else ""

        if available:
            base_text = f"直行{direct_count}便 / 全{len(formatted_flights)}便" if direct_count else f"全{len(formatted_flights)}便"
            seats_text = base_text + note_str
        else:
            seats_text = f"空席なし{note_str}"

        return Availability(
            query=query,
            available=available,
            seats_text=seats_text,
            flights=formatted_flights,
            dynamic_count=dynamic_count,
            unknown_count=unknown_count,
            parse_failed_count=parse_failed_count,
        )

