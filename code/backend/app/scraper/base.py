"""スクレイパーの共通の型。中身を差し替えられるようにしておく。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class RetryableError(Exception):
    """時間を置けば成功するかもしれないエラー（タイムアウトなど）"""


class SessionExpiredError(RetryableError):
    """ログインが切れた → ログインし直してから再試行する"""


class BlockedError(Exception):
    """ボット対策（CAPTCHAなど）を検知 → 突破は試みず、すぐに検索を止める"""


class CashDisplayError(Exception):
    """United検索結果が現金表示になっているエラー（空席なしと誤判定させない）"""


@dataclass
class Availability:
    query: dict
    available: bool
    seats_text: str = ""                          # 例："空席あり" / "残りわずか"
    flights: list[dict] = field(default_factory=list)
    dynamic_count: int = 0                        # ANA発券対象外のダイナミックプライス枠件数
    unknown_count: int = 0                        # 運賃クラス不明の件数
    parse_failed_count: int = 0                   # 抽出に失敗したフライトカード件数


class AwardProvider(ABC):
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def open(self) -> None:
        """ブラウザ起動やログインなどの準備（必要なら上書き）"""

    def close(self) -> None:
        """後片付け（必要なら上書き）"""

    def relogin(self) -> None:
        """ログインし直す（必要なら上書き）"""

    @abstractmethod
    def search(self, query: dict) -> Availability:
        """1件（出発地・目的地・日付）を検索する"""
