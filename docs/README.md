# ANA特典航空券 空席サーチ（Star Alliance Award Search）

## 1. プロジェクトの目的
ANAマイレージクラブ会員が、スターアライアンス提携航空会社の特典航空券（片道）の **空席日程・直行/経由便・必要マイル数** を、広域エリア（北米・欧州・東南アジア・ハワイ）または個別都市ごとに一括検索するためのWebアプリケーションです。

## 2. システム構成
| 役割 | 技術・コンポーネント |
|---|---|
| フロントエンド画面 | HTML5 + CSS3（Premium Lounge Theme）+ JavaScript（EventSource / SSE） |
| バックエンドAPI・SSE配信 | FastAPI（Dockerコンテナ `api`・ポート8000） |
| 非同期検索ワーカー | Celery（Dockerコンテナ `worker`・並列数1） |
| ジョブ管理・結果キャッシュ | Redis（Dockerコンテナ `redis`） |
| ブラウザ自動操作API | FastAPI + Playwright Chrome（Windowsホスト側 `host_scraper_api.py`・ポート8001） |

```text
antigravity/
├─ config/
│  └─ ana-award-search.env       # 機密情報・環境変数（プロジェクト外で安全に管理）
└─ projects/ana-award-search/
   ├─ docs/
   │  └─ README.md               # 本ドキュメント
   └─ code/
      ├─ docker-compose.yml      # Dockerサービス定義（api, worker, redis）
      ├─ host_scraper_api.py     # Windowsホスト側でChromeを制御するスクレイパーAPI
      ├─ backend/
      │  ├─ Dockerfile
      │  ├─ requirements.txt
      │  └─ app/
      │     ├─ main.py           # FastAPI エンドポイント・SSE配信・自動キュー破棄
      │     ├─ tasks.py          # Celery 非同期検索タスク・リトライ制御
      │     ├─ progress.py       # Redis による進捗・結果・キャンセル管理
      │     ├─ areas.py          # エリア・空港コード・日本語都市名定義
      │     ├─ routes.py         # 直行便の就航路線定義
      │     ├─ config.py         # 環境変数からの設定読み込み
      │     └─ scraper/          # 検索プロバイダ（ua.py / mock.py）
      └─ frontend/
         ├─ index.html           # 画面レイアウト
         ├─ style.css            # プレミアム・ラウンジ風スタイルシート
         └─ app.js               # リアルタイム件数計算・絞込・ソート・CSV出力制御
```

## 3. 主要機能とアップデート内容
- **ワンクリック起動**：デスクトップの「マイル検索アプリ.vbs」から、Dockerコンテナ群・Windowsホスト側API・ブラウザ画面を一括起動できます。
- **自動ログイン＆エラー自動リセット機能**：
  - `config/ana-award-search.env` の認証情報を用いて自動ログインします。
  - 検索中に一時的なアクセス制限（`We're sorry...`）を検知した場合、自動でCookieを消去してブラウザセッションを再構築・再検索します。
- **リアルタイム検索件数＆目安時間プレビュー**：検索ボタンを押す前に、指定した期間・エリアでの検索区間数と所要時間の目安を自動計算して表示します。
- **リアルタイム絞り込み・並び替え・カレンダー連動**：
  - 検索結果から「直行便のみ / 経由便のみ」「目的地の空港別」で即座にフィルタリング可能。
  - 「日付順」「必要マイルが少ない順」「直行便優先」での並び替えに対応。
  - カレンダーの空席日をクリックすると、その日のフライト一覧へ連動して絞り込みます。
- **2WAY予約・確認リンク ＆ CSV保存**：
  - 区間・日付を自動コピーして開く「ANA特典予約へ ↗」ボタンと、該当便を直接開く「UAで確認 ↗」ボタンを搭載。
  - 検索結果をExcel対応のCSVファイル（BOM付きUTF-8）としてワンクリックで保存できます。

## 4. セットアップと起動手順
1. **設定ファイルの準備**
   - `antigravity/config/ana-award-search.env` に以下の設定を記述します：
     ```env
     SCRAPER_PROVIDER=ua
     UA_USERNAME=ご自身のマイレージ番号またはメールアドレス
     UA_PASSWORD=ご自身のパスワード
     ```
2. **依存ライブラリのセットアップ（初回のみ）**
   - Docker Desktop を起動します。
   - Windowsホスト側のPython仮想環境（`code/host_venv`）に `fastapi`, `uvicorn`, `playwright`, `beautifulsoup4`, `python-dotenv` をインストールします。
3. **日常の起動方法**
   - デスクトップの **「マイル検索アプリ.vbs」** をダブルクリックすると、すべてのサーバーが起動し、自動でブラウザ（`http://localhost:8000`）が開きます。
