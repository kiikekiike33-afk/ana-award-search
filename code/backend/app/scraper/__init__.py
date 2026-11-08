"""スクレイパーの切り替え（環境変数 SCRAPER_PROVIDER で選択）"""
from ..config import settings


def get_provider():
    """設定に応じた検索プロバイダを返す（デフォルトはユナイテッド航空経由の 'ua'）"""
    if settings.scraper_provider == "mock":
        from .mock import MockProvider
        return MockProvider()
    from .ua import UAProvider
    return UAProvider()

