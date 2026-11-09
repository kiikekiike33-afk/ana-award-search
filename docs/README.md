# -*- coding: utf-8 -*-
# ANA特典航空券 空席サーチ（スターアライアンス提携社特典枠一括検索）

ユナイテッド航空（UA）公式サイトの特典航空券検索機能を利用し、スターアライアンス提携社特典枠（ANAマイルで発券可能なエコノミー/ビジネスクラス空席）を一括高速検索するWebアプリケーションです。

## 1. 目的と特徴
- **ANA特典枠の高精度サーチ**：スターアライアンス加盟各社共通のセーバー特典クラス（エコノミー: X / ビジネス: I / ファースト: O）のみを厳密に抽出し、UA自社専用枠やダイナミックプライシング枠（JN等）を自動除外。
- **期間×エリア一括検索**：指定した期間（最大1年）およびエリア（ヨーロッパ、北米、東南アジア、オセアニア、インド、ハワイ等）内の複数都市・複数日程を一括で自動検索。
- **セッション安全保護**：ユナイテッド航空の2段階認証やログイン状態を保護するためCookieの勝手な消去は行わず、一時アクセス制限（`We're sorry`）発生時は空席なしと誤認させずに安全にスキップ＆通知。

## 2. システム構成
- **バックエンド**：Python FastAPI + Celery + Redis（Docker環境で稼働）
- **フロントエンド**：HTML5 + CSS3 + Vanilla JavaScript（SSEによるリアルタイム進捗配信・リスト/カレンダー表示）
- **ホスト側API**：Windowsホスト上で常駐するPlaywright API（ポート8001、共有トークン認証付き）。常駐Chromeによる高速描画＆ANA特典予約画面への自動入力中継を担当。

```text
ana-award-search/
  ├─ code/
  │   ├─ host_scraper_api.py   # Windows側Chrome常駐・Playwright中継API
  │   ├─ docker-compose.yml    # コンテナ構成（backend, worker, redis）
  │   ├─ backend/
  │   │     ├─ Dockerfile      # 軽量バックエンドイメージ（Playwright除外）
  │   │     ├─ requirements.txt# 依存ライブラリ（バージョン固定）
  │   │     ├─ app/main.py     # FastAPI Web API
  │   │     ├─ app/tasks.py    # Celery 検索タスク
  │   │     └─ scraper/        # 検索プロバイダ（ua.py / mock.py）
  │   └─ frontend/
  │         ├─ index.html      # 画面レイアウト
  │         ├─ style.css       # プレミアム・ラウンジ風スタイルシート
  │         └─ app.js          # リアルタイム件数計算・絞込・ソート・CSV出力制御
  └─ docs/
        └─ README.md           # 本仕様書
```

## 3. 主要機能とアップデート内容
- **ワンクリック起動**：デスクトップの「マイル検索アプリ.vbs」から、Dockerコンテナ群・Windowsホスト側API・ブラウザ画面を一括起動できます。
- **自動ログイン＆セッション保護機能**：
  - `config/ana-award-search.env` の認証情報を用いて自動ログインします。
  - ログイン状態（Cookieおよび2段階認証トークン）を維持・保護するため、Cookieの消去は行いません。
  - 検索中に一時的なアクセス制限（`We're sorry...`）を検知した場合、「空席なし」と誤判定させずに該当区間をスキップしてSSE通知し、3回連続発生時はアカウント保護のためジョブを自動停止します。
- **リアルタイム検索件数＆目安時間プレビュー**：検索ボタンを押す前に、指定した期間・エリアでの検索区間数と所要時間の目安を自動計算して表示します。
- **リアルタイム絞り込み・並び替え・カレンダー連動**：
  - 検索結果から「直行便のみ / 経由便のみ」「目的地の空港別」で即座にフィルタリング可能。
  - 「日付順」「必要マイルが少ない順」「直行便優先」での並び替えに対応。
  - カレンダーの空席日をクリックすると、その日のフライト一覧へ連動して絞り込みます。
- **2WAY予約・確認リンク ＆ CSV保存**：
  - 区間・日付を自動コピーして開く「ANA特典予約へ ↗」ボタンと、該当便を直接開く「UAで確認 ↗」ボタンを搭載。
  - 検索結果をExcel対応のCSVファイル（BOM付きUTF-8）としてワンクリックで保存できます。

## 4. セットアップと起動手順

### A. 通常利用（実サイト検索モード）
1. **設定ファイルの準備**
   - `antigravity/config/ana-award-search.env` またはリポジトリルートの `.env` に以下の設定を記述します：
     ```env
     SCRAPER_PROVIDER=ua
     HOST_API_TOKEN=your_secure_token_here
     UA_USERNAME=your_united_mileage_number
     UA_PASSWORD=your_united_password
     ANA_MEMBER_ID=your_ana_number
     ANA_PASSWORD=your_ana_web_password
     ```
2. **起動**
   - `マイル検索アプリ.vbs` をダブルクリックして起動します。

### B. リポジトリ単体起動（Mock モード / 開発・動作確認用）
認証情報や外部 config フォルダがなくても、リポジトリ単体ですぐに動作確認が可能です。
1. **環境変数の指定（任意）**
   - リポジトリルートに `.env` を作成し `SCRAPER_PROVIDER=mock` と記述するか、`.env.example` のまま起動します。
2. **Docker Compose の起動**
   ```bash
   cd code
   docker compose up -d
   ```
3. **ブラウザで確認**
   - ブラウザで `http://localhost:8000` にアクセスします。
   - 画面で出発地・目的地・期間を選択し、「空席サーチ開始」をクリックすると、モックデータによる空席検索・進捗更新・一覧表示・カレンダー表示の一連のフローが確認できます。
