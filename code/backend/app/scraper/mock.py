"""開発用の仮データ。ANAには一切アクセスしない。"""
import hashlib
import time

from .base import AwardProvider, Availability


class MockProvider(AwardProvider):
    def search(self, q: dict) -> Availability:
        time.sleep(0.2)
        # 同じ条件なら毎回同じ結果になる疑似乱数（約20%の確率で「空席あり」）
        h = int(hashlib.md5(str(sorted(q.items())).encode()).hexdigest(), 16)
        ok = h % 5 == 0
        return Availability(q, ok, "空席あり（仮データ）" if ok else "",
                            [{"flight_no": f"NH{h % 900 + 100}"}] if ok else [])
