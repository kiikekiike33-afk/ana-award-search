# ✈ ANA Star Alliance Award Search (ANA特典航空券 空席サーチ)

スターアライアンス提携航空会社（ANA・ユナイテッド航空など）の国際線特典航空券（片道）の **空席日程・直行/経由便・必要マイル数** を、広域エリア（北米・欧州・東南アジア・ハワイ）または個別都市ごとに一括検索できるWebアプリケーションです。

---

## 🌟 主な特徴

- **広域エリア一括検索**: 北米・ヨーロッパ・東南アジア・ハワイなどの主要都市をカレンダー形式でまとめて空席調査。
- **純粋な直行便（ノンストップ便）の完全抽出**: 経由便を除外したノンストップ便のみの絞り込み表示に対応。
- **ANA特典予約画面への自動入力**: 検索結果から「ANA特典予約へ（自動入力） ↗」を押すと、Chromeが最前面に開き、出発地・目的地・日付・クラス・人数が自動セットされます。
- **リアルタイム進捗配信**: SSE（Server-Sent Events）により、検索中の進捗率や残り時間をリアルタイムに画面表示。
- **スマホ対応**: レスポンシブ対応のプレミアム・ラウンジ風UI。同一Wi-Fi内のスマートフォンからもアクセス可能。

---

## 🏗 システム構成

```text
ana-award-search/
├── .env.example              # 環境変数のサンプルテンプレート
├── .gitignore                # 機密情報・Cookie・仮想環境を除外する安全設定
├── MUSE.md                   # Muse (AIコーディングエージェント) 向け開発ガイド
├── README.md                 # 本ドキュメント
├── docs/
│   └── README.md             # プロジェクト仕様書
└── code/
    ├── docker-compose.yml     # Dockerサービス定義 (api, worker, redis)
    ├── host_scraper_api.py    # Windowsホスト側 Playwright Chrome 制御API (Port 8001)
    ├── backend/               # FastAPI バックエンド & Celery 検索ワーカー (Port 8000)
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── app/
    │       ├── main.py        # APIエンドポイント・SSE配信・ANA自動入力中継
    │       ├── tasks.py       # Celery 検索タスク・リトライ・安全中断制御
    │       ├── areas.py       # 空港コード・都市名・検索クエリ展開
    │       ├── routes.py      # 直行便就航路線マスタ
    │       └── scraper/       # 検索プロバイダ (ua.py / mock.py)
    └── frontend/              # プレミアム・ラウンジ風 Web UI
        ├── index.html
        ├── style.css
        └── app.js
```

| コンポーネント | 役割 | 動作環境 |
|---|---|---|
| **Frontend UI** | 空席一覧・カレンダー・条件指定・CSV出力 | ブラウザ (`http://localhost:8000`) |
| **Backend API** | ジョブ受付、進捗配信 (SSE)、マスタ管理 | Docker コンテナ `code-api-1` |
| **Search Worker** | 非同期検索の実行、中断・リトライ制御 | Docker コンテナ `code-worker-1` |
| **Job Queue** | 進捗ステータス、検索結果キャッシュ | Docker コンテナ `code-redis-1` |
| **Host Scraper API** | 実Chromeブラウザ操作、ANA/UAログイン制御 | Windows ホスト側 Python (`Port 8001`) |

---

## 🚀 セットアップ & 起動手順

### 1. 前提条件
- **Windows 10 / 11**
- **Docker Desktop** がインストールされていること
- **Python 3.11+** (Windowsホスト用)
- **Google Chrome**

### 2. 環境変数の設定
`.env.example` を参考に、プロジェクト外の安全な場所（またはルート）に設定ファイル `ana-award-search.env` を用意します。
```env
ANA_MEMBER_ID=あなたのANAお客様番号
ANA_PASSWORD=あなたのANAパスワード
UA_USERNAME=あなたのユナイテッド航空IDまたはメールアドレス
UA_PASSWORD=あなたのユナイテッド航空パスワード
SCRAPER_PROVIDER=ua
```

### 3. コンテナとホストAPIの起動
```powershell
# 1. code ディレクトリへ移動
cd code

# 2. Docker コンテナ (api, worker, redis) の起動
docker compose up -d

# 3. ホスト側スクレイパーAPIの起動 (ポート 8001)
python -m uvicorn host_scraper_api:app --host 0.0.0.0 --port 8001
```

### 4. アプリを開く
ブラウザで以下のURLを開きます：
- パソコンから: `http://localhost:8000`
- 同一Wi-Fiのスマホから: `http://<パソコンのローカルIP>:8000` (例: `http://192.168.3.5:8000`)

---

## 🔒 セキュリティと認証について

- **機密情報の保護**: パスワードや認証キーはコードに直書きせず、すべて外部環境変数ファイルから読み込みます。
- **セッション保護**: 2段階認証コードの入力画面が出た場合はその場で停止し、Cookie情報を保持したまま手打ち完了を待ちます（Cookieの勝手な消去や連続リトライは行われません）。
