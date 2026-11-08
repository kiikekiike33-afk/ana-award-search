"""設定。値はすべて環境変数（.env）から読み込み、コードには直接書かない。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """アプリケーション全体の動作設定"""
    model_config = SettingsConfigDict(extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    scraper_provider: str = "ua"            # ua（実サイト検索） | mock（テスト用仮データ）
    min_delay_sec: float = 4.0              # 検索ごとの最小待機秒数
    max_delay_sec: float = 9.0              # 検索ごとの最大待機秒数
    long_break_every: int = 50              # この件数ごとに長めの休憩を入れる
    long_break_sec: float = 90.0            # 長めの休憩の秒数
    max_retries: int = 3                    # エラー時の最大再試行回数
    max_queries_per_job: int = 2000         # 1回の検索ジョブあたりの上限件数


settings = Settings()

