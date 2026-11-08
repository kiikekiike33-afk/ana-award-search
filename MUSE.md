# 🤖 Muse Code / AI Agent Development Guide

このファイルは、**Muse（Muse Code / Meta Muse）** などのAIコーディングエージェントが当リポジトリ（`ana-award-search`）を理解し、安全にコード編集・機能拡張を行うための仕様ガイドです。

---

## 1. プロジェクト概要

- **名称**: ANA特典航空券 空席サーチ (Star Alliance Award Search)
- **主要言語**: Python 3.12 (FastAPI, Celery, Playwright), HTML5 / CSS3 / JavaScript (Vanilla JS)
- **構成**:
  - `Docker環境`: FastAPI (`code-api-1`), Celery Worker (`code-worker-1`), Redis (`code-redis-1`)
  - `Windowsホスト環境`: Playwright Chrome API (`host_scraper_api.py`: ポート8001)
  - `フロントエンド`: 静的ファイル群 (`code/frontend/`)

---

## 2. 最重要の安全ルール & 設計制約（遵守必須）

AIエージェントがコードを編集する際は、以下のルールを**絶対に厳守**してください：

1. **機密情報の保護 (No Hardcoded Secrets)**:
   - ANAやユナイテッド航空のID・パスワード、APIキーをソースコード内に直接書き込まないこと。
   - 必ず `config/ana-award-search.env` または環境変数から読み込む設計を維持すること。
2. **Cookie・セッションの維持 (Do NOT clear cookies)**:
   - `host_scraper_api.py` 内で、一時的なエラー（`We're sorry...` 等）に遭遇した際に **`clear_cookies()` などのセッション破棄処理を勝手に追加しないこと**。ユーザーの2段階認証セッションが失われ、無限認証ループが発生する原因となります。
3. **2段階認証待機時の完全停止 (No Aggressive Retry)**:
   - 確認コード入力画面を検知した場合、手打ち完了を待機し、タイムアウト時は即時中断（HTTP 401）すること。裏で勝手に再ログインや別都市への検索リトライを行ってはならない。
4. **直行便フィルタの厳格性**:
   - `direct_only=True` の検索クエリでは、経由便（`not is_direct`）をバックエンド (`ua.py`) とフロントエンド (`app.js`) の両面で完全に除外するロジックを保持すること。

---

## 3. ディレクトリ構成とファイル役割

```text
ana-award-search/
├── .env.example              # 環境変数テンプレート
├── .gitignore                # Git除外設定 (ua_profile, host_venv, .env等を厳格に除外)
├── README.md                 # ユーザー向け全体ドキュメント
├── MUSE.md                   # 本ファイル (Muse向け開発ガイド)
├── docs/                     # 詳細ドキュメント
└── code/
    ├── docker-compose.yml     # api, worker, redis の定義
    ├── host_scraper_api.py    # Windowsホスト側で常駐し、実ChromeをCDP経由で操作するFastAPIサーバー
    ├── backend/
    │   ├── Dockerfile         # Python 3.12-slim ベース
    │   ├── requirements.txt   # バックエンド依存パッケージ
    │   └── app/
    │       ├── main.py        # API受付 (POST /api/searches, POST /api/ana-autofill 等)
    │       ├── tasks.py       # Celeryタスク実行、進捗通知 (Redis Pub/Sub)
    │       ├── progress.py    # Redisによるジョブ管理・キャンセル・スナップショット
    │       ├── areas.py       # 空港コード、就航都市、検索クエリの組み合わせ生成
    │       ├── routes.py      # 直行便の路線定義 (羽田/成田の就航地)
    │       ├── config.py      # Pydantic Settings
    │       └── scraper/
    │           ├── base.py    # AwardProvider 抽象クラス
    │           ├── ua.py      # ユナイテッド航空スクレイピング & データ正規化
    │           └── mock.py    # 開発・テスト用モックプロバイダ
    └── frontend/
        ├── index.html         # 検索条件入力フォーム、統計バー、結果テーブル
        ├── style.css          # シャンパンゴールド×ディープネイビーのラウンジUI
        └── app.js             # SSE接続受信、リアルタイム件数計算、ANA自動入力呼び出し
```

---

## 4. よく使う開発コマンド

### Docker コンテナの管理 (code ディレクトリで実行)
```powershell
# 起動
docker compose up -d

# ログ確認
docker compose logs -f worker
docker compose logs -f api

# 再起動 (コード変更反映)
docker compose restart api worker
```

### ホスト側スクレイパーAPIの起動
```powershell
python -m uvicorn host_scraper_api:app --host 0.0.0.0 --port 8001
```

### Redisキューの初期化 (スタックしたジョブの強制クリア)
```powershell
docker compose exec redis redis-cli FLUSHALL
```

---

## 5. コミュニケーション方針
- 作成するコードのコメントおよびドキュメントは、原則として **日本語** で分かりやすく記述してください。
