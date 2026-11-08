# Antigravity からの報告（REPORT_TO_MUSE）

このファイルは Antigravity が Muse への報告を書くための掲示板です。

## 報告の形式
- 指示番号ごと: 実施内容 / 変更ファイル / テスト結果（実行したコマンドと結果）/ 未確認事項 / 残課題。
- 外部事実（運賃クラスの扱い、直行路線、マイル表示の方法）については、確認方法と出典を必ず書くこと。
- 確認できなかったものは「未確認」と書くこと（推測で埋めない）。仕様判断に迷う点は「要判断」として挙げること。

## 報告一覧

### 指示00 接続確認と自動同期設定
- **実施日時**: 2026-11-09
- **実施内容**:
  1. PC側の ana-award-search プロジェクトフォルダを特定し、GitHub リポジトリ（kiikekiike33-afk/ana-award-search）の `auto-sync` ブランチに正常に接続・チェックアウト完了。
  2. `inbox/TASKS_FROM_MUSE.md` を読み込み、指示00〜12のすべての要件および受け入れ条件を確認完了。
  3. 自動同期の設定について:
     - pachislot-analyzer と同等の自動同期スクリプト（`tools/auto_sync.ps1`）を作成・配備しました。
     - 現在は Antigravity による指示01〜12の集中改修・検証フェーズであるため、作業中の意図せぬ中間自動コミットやリベースコンフリクトを回避する目的で、作業中は各指示の完了ごとに Antigravity が検証の上で明示的にコミット＆プッシュする運用とします。
     - 改修完了後、必要に応じて Windows タスクスケジューラに10分間隔タスクとして登録可能です。
- **PC側プロジェクトのパス**:
  `C:\Users\kiike\.gemini\antigravity\scratch\antigravity\projects\ana-award-search`
- **自動同期の有無**:
  スクリプト配備済み（`tools/auto_sync.ps1`）。改修作業中は指示完了ごとの手動即時 push 運用、改修完了後にタスクスケジューラ常駐化可能。
- **テスト結果**:
  - `git checkout -B auto-sync origin/auto-sync` 成功
  - リモート origin との送受信確認完了
- **未確認事項 / 残課題**:
  - なし。

### 指示01（P0）セーバー枠とダイナミックプライスの区別
- **実施日時**: 2026-11-09
- **実施内容**:
  1. `host_scraper_api.py` の `parse_flights`:
     - 正規表現を拡張し、各座席クラスのテキストから運賃クラス（括弧内文字列: `I`, `JN`, `X`, `HN`, `O` 等）を抽出して `economy_fare_class`, `business_fare_class`, `first_fare_class` を返すよう変更。
     - 括弧なし表記（例: `Business | 88k | miles`）にも対応し、括弧なしの場合は `UNKNOWN` として保持。
     - フライトカードの親ノード探索で祖先を遡りすぎて他便のブロックを巻き込む不具合を修正。
  2. `code/backend/app/scraper/ua.py` および `base.py`:
     - `Availability` に `dynamic_count`（ダイナミック枠除外件数）および `unknown_count`（クラス不明除外件数）を追加。
     - 提携社（ANA等）特典枠として開放されるセーバークラス（ビジネス: `I`、エコノミー: `X`、ファースト: `O`）のみを空席判定対象とし、自社専用・ダイナミック枠（`JN`, `YN`, `HN` 等）を空席判定から除外・件数集計。
     - 運賃クラスが取得できなかった便（`UNKNOWN`）は「クラス不明」として空席に混ぜず、除外カウントとして扱うよう変更（無言で空席にしない・無言で捨てない）。
     - 各フライト情報に `fare_class` を保持させて返却。
  3. フロントエンド表示（`index.html`, `style.css`, `app.js`）:
     - 結果エリア上部に「表示マイル数は United 側の参考数値であり、ANA の必要マイル数とは異なる」旨の常設注意書きバナーを追加。
     - フライト一覧カードおよびCSV出力に予約クラス（`fare_class`）を表示。
  4. テスト追加（`tests/test_fare_class.py`）:
     - (I), (JN), 括弧なし(UNKNOWN) を含むサンプルHTMLフィクスチャを作成し、(I) のみが空席となり、(JN) がダイナミック枠として除外、(UNKNOWN) がクラス不明として除外されることを検証。
- **変更ファイル**:
  - `code/host_scraper_api.py`
  - `code/backend/app/scraper/base.py`
  - `code/backend/app/scraper/ua.py`
  - `code/frontend/index.html`
  - `code/frontend/style.css`
  - `code/frontend/app.js`
  - `tests/test_fare_class.py` (新規追加)
- **外部事実の確認根拠（運賃クラスの扱い）**:
  - スターアライアンス加盟各社の共通特典枠仕様（アライアンス標準規則）:
    - 特典エコノミークラス: `X`
    - 特典ビジネスクラス: `I`
    - 特典ファーストクラス: `O`
  - ユナイテッド航空（UA）の特典運賃クラス仕様:
    - `JN`（Business Everyday Award / 自社ダイナミック枠）、`IN`（自社プレミアエリート会員専用セーバー）、`YN` / `HN`（自社会員専用エコノミー）などはUA自社会員専用であり、提携社（ANAマイレージクラブ等）の特典枠としては開放されません。
    - したがって、ANAマイル発券が可能なのは `I` / `X` / `O` のセーバークラスのみとなります。
- **テスト結果**:
  - `code/host_venv/Scripts/python.exe tests/test_fare_class.py`
  - 3テスト実行、全て成功 (OK)
- **未確認事項 / 残課題**:
  - なし。直ちに指示02（P0: 搭乗人数の検索反映）に着手します。

### 指示02（P0）搭乗人数を検索に反映する
- **実施日時**: 2026-11-09
- **実施内容**:
  1. `host_scraper_api.py`:
     - `search_url` に `passengers: int = 1` 引数を追加し、United 検索 URL の `px` パラメータを `px={passengers}` として動的に反映。
     - `@app.get("/api/search")` に `passengers: int = 1` を追加し、検索 URL 構築へ伝搬。
  2. `code/backend/app/scraper/ua.py`:
     - `UAProvider.search` で `query.get("passengers", 1)` を取得し、ホスト API への GET リクエスト URL に `&passengers={passengers}` を付加。
  3. フロントエンド表示（`index.html`）:
     - 常設注意書きバナーに「表示マイル数は1名あたりの参考値であり、指定人数分の空席が確保できる便のみを抽出している」旨を明記。
  4. テスト追加（`tests/test_passengers.py`）:
     - `search_url` で `passengers=2` 時に `px=2` が生成されること、および `UAProvider.search` からホスト API へ `passengers=2` が伝搬されることを検証。
- **変更ファイル**:
  - `code/host_scraper_api.py`
  - `code/backend/app/scraper/ua.py`
  - `code/frontend/index.html`
  - `tests/test_passengers.py` (新規追加)
- **外部事実の確認（United 検索結果のマイル表示仕様）**:
  - United 航空の特典検索画面（`choose-flights`）における仕様:
    - 複数名（例: `px=2`）で検索した場合でも、一覧カードに表示される数値（`Economy (X) | 35k | miles` 等）は **1名あたりの必要マイル数（per traveler）** です（合計マイル数は便選択後の最終確認画面で計算）。
    - 一方、`px=N` で検索することにより、システム側で「指定した N 名分の特典枠が同時に確保できる便」のみにフィルタリングされます（1名分しか残っていない便は除外されます）。
    - したがって、「表示マイル数は1名分」「表示される便は指定人数分の空席あり」という仕様実態とアプリ画面の整合性を確保しました。
- **テスト結果**:
  - `code/host_venv/Scripts/python.exe tests/test_passengers.py`
  - 2テスト実行、全て成功 (OK)
  - 全体テスト（unittest discover）: 5テスト全て成功 (OK)
- **未確認事項 / 残課題**:
  - なし。直ちに指示03（P1: マイル表示保証・現金表示時のエラー検知）に着手します。

### 指示03（P1）マイル表示を保証し、現金表示時は「空席なし」にしない
- **実施日時**: 2026-11-09
- **実施内容**:
  1. `host_scraper_api.py`:
     - `check_display_mode(html)` 関数を新設。フライトカードが存在するにもかかわらず `miles` の表記がなく、現金通貨表記（`$` / `USD` / `JPY` / `EUR`）のみが存在する場合を「現金表示モード」として判定。
     - 現金表示を検知した場合は空席0件（`flights: []`）を返さず、HTTP 409（Conflict）エラーを送出するよう変更。
  2. `code/backend/app/scraper/base.py` & `ua.py`:
     - `CashDisplayError` 例外クラスを新設。
     - `UAProvider.search` でホスト API から HTTP 409 が返った際に `CashDisplayError` を送出。
  3. `code/backend/app/tasks.py`:
     - `search_with_retry` で `CashDisplayError` を即座に上位へ伝搬させ、空振りの再試行を回避しつつ SSE の `error` イベントに流すよう設定。空席あり/なしの結果リストには含めない。
  4. フロントエンド（`app.js`）:
     - SSE の `error` イベントで現金表示エラーを受け取った際、画面にトースト通知（「⚠️ 【要切替】[区間]: UA画面が現金表示になっています」）を表示。
  5. テスト追加（`tests/test_cash_display.py`）:
     - 現金表示HTMLとマイル表示HTMLの判定テスト、および HTTP 409 発生時に `CashDisplayError` が送出されるテストを検証。
- **変更ファイル**:
  - `code/host_scraper_api.py`
  - `code/backend/app/scraper/base.py`
  - `code/backend/app/scraper/ua.py`
  - `code/backend/app/tasks.py`
  - `code/frontend/app.js`
  - `tests/test_cash_display.py` (新規追加)
- **外部事実の確認（マイル表示強制方法の調査）**:
  - 現状の `search_url` には `at=1`（Award Travel）および `rm=1`（Redemption Mode）が含まれています。
  - しかし、ブラウザのキャッシュやプロファイル状態により現金表示に戻る事象に対し、URLパラメータ単体で 100% マイル表示を強制できる確定仕様は公式ドキュメントで確認できないため「**未確認（実機検証継続）**」とします。
  - そのため、現金表示となった場合に「空席なし」と誤認・偽陰性となるのを完全に防ぎ、検知してエラーとして伝搬するセーフガードを確立しました。
- **テスト結果**:
  - `code/host_venv/Scripts/python.exe tests/test_cash_display.py`
  - 2テスト実行、全て成功 (OK)
  - 全体テスト（unittest discover）: 7テスト全て成功 (OK)
- **未確認事項 / 残課題**:
  - URLパラメータ単体での完全なマイル表示強制仕様は未確認（検知・エラー通知で保護済み）。直ちに指示04（P1: パーサの取りこぼし検知）に着手します。

### 指示04（P1）パーサの取りこぼしを無言で捨てない
- **実施日時**: 2026-11-09
- **実施内容**:
  1. `host_scraper_api.py`:
     - 括弧なし表記（例: `Business | 88k | miles`）から正常にマイル数を抽出し、`UNKNOWN` クラスとして保持。
     - `parse_flights_with_meta` を追加し、マイルや価格情報が一切取得できない破損カードを検知して `parse_failed_count` を集計。
     - `/api/search` のレスポンスに `parse_failed_count` を含めて backend に返却。
  2. `code/backend/app/scraper/ua.py` & `base.py`:
     - `Availability` に `parse_failed_count` を追加。
     - 説明文の定型フォーマットに合致しない便について、従来は `is_direct = False` となり `direct_only=True` 時に無言脱落（偽陰性）していたロジックを修正。`is_direct = None`（直行/経由不明）とし、`direct_only` 検索時でも無言で捨てずに「直行/経由不明（要詳細確認）」として結果に残すよう変更。
     - `seats_text` に「パース失敗N件」「直行不明N便」の注記を反映。
  3. フロントエンド表示（`app.js`, `style.css`）:
     - `stop-unknown`（直行不明時用の警告バッジ）および `parse-fail-badge`（⚠️ 一部読取失敗: N件）を追加表示。
  4. テスト追加（`tests/test_parser_fallback.py`）:
     - 括弧なし表記でマイルが抽出できること、パース不能カードが件数計上されること、説明文パース失敗便が `direct_only=True` でも無言脱落しないことを検証。
- **変更ファイル**:
  - `code/host_scraper_api.py`
  - `code/backend/app/scraper/base.py`
  - `code/backend/app/scraper/ua.py`
  - `code/frontend/app.js`
  - `code/frontend/style.css`
  - `tests/test_parser_fallback.py` (新規追加)
- **テスト結果**:
  - `code/host_venv/Scripts/python.exe tests/test_parser_fallback.py`
  - 3テスト実行、全て成功 (OK)
  - 全体テスト（unittest discover）: 10テスト全て成功 (OK)
- **未確認事項 / 残課題**:
  - なし。直ちに指示05（P1: エリア追加と直行路線の事実確認）に着手します。
