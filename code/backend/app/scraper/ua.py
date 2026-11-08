"""ユナイテッド航空（UA）の検索APIを経由してスターアライアンス特典枠を取得するプロバイダ"""
import json
import re
import urllib.error
import urllib.request
from .base import AwardProvider, Availability, BlockedError, RetryableError


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

        # Dockerコンテナの中から、Windowsホスト（host.docker.internal）の8001番ポートへ通信
        url = f"http://host.docker.internal:8001/api/search?origin={origin}&destination={dest}&date={date_str}"

        try:
            # ブラウザの自動操作（ログイン時の確認コード手打ち待機を含む）が終わるまで最長360秒（6分）待機
            req = urllib.request.Request(url, headers={"User-Agent": "AnaAwardSearchWorker/1.0"})
            with urllib.request.urlopen(req, timeout=360) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # 認証コード待ちタイムアウト時はリトライや次の都市への移動を一切行わず、その場で検索ジョブ全体を停止する
                raise BlockedError("認証コード入力待ちのため検索を一時停止しました（再度のログイン試行は行いません）。Chrome画面でコードを入力してログイン完了後、もう一度検索を開始してください。")
            raise RetryableError(f"Windows側のAPIサーバーとの通信に失敗しました: {e}")
        except Exception as e:
            raise RetryableError(f"Windows側のAPIサーバーとの通信に失敗しました: {e}")

        raw_flights = data.get("flights", [])
        cabin = query.get("cabin", "economy")
        direct_only = query.get("direct_only", True)

        formatted_flights = []
        for f in raw_flights:
            eco = f.get("economy_miles", "N/A")
            bus = f.get("business_miles", "N/A")
            desc = f.get("flight_description", "")

            # 検索条件のクラスに応じたマイル数を取得（ファースト指定時はビジネス枠を参照）
            target_miles = eco if cabin == "economy" else bus

            # 「55k」などの数字が含まれていない場合（N/Aなど）は空席なしとみなしてスキップ
            if not re.search(r"\d", str(target_miles)):
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
                is_direct = False
                stop_label = "詳細確認"
                flight_no = f"💺 {target_miles}"

            # 「直行便のみ」が有効な場合は、経由便（乗継便）や他空港発着便を完全に除外し、純粋な直行便のみに絞る
            if direct_only:
                if not is_direct:
                    continue
                if orig_code != origin or dest_code != dest:
                    continue

            formatted_flights.append({
                "flight_no": flight_no,
                "miles": target_miles,
                "miles_num": miles_num,
                "economy_miles": eco,
                "business_miles": bus,
                "orig_code": orig_code,
                "dest_code": dest_code,
                "dep_time": dep_time,
                "arr_time": arr_time,
                "is_direct": is_direct,
                "stop_label": stop_label,
            })

        # 見やすいように「直行便を最優先」→「必要マイルが少ない順」に並び替える
        formatted_flights.sort(key=lambda x: (0 if x["is_direct"] else 1, x["miles_num"]))

        available = len(formatted_flights) > 0
        direct_count = sum(1 for x in formatted_flights if x["is_direct"])
        seats_text = f"直行{direct_count}便 / 全{len(formatted_flights)}便" if direct_count else f"全{len(formatted_flights)}便"

        return Availability(
            query=query,
            available=available,
            seats_text=seats_text if available else "空席なし",
            flights=formatted_flights,
        )

