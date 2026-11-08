"""
ユナイテッド航空 検索API（Windows側で動かす中継サーバー / ポート8001）

設計のポイント:
- ユナイテッドはChromeを閉じるとログインが無効になるため、Chromeは「1回だけ起動して閉じない」
- Chromeは普段は画面の外（見えない場所）に置いておく
- ログインが必要になった時だけ、Chromeを画面内に移動して自動ログイン
  （失敗した時・確認コードが必要な時だけ、手動ログインをお願いするダイアログを出す）
"""
import os
import re
import asyncio
import ctypes
import traceback
from datetime import date, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# ---------- 設定 ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_app_env():
    """環境変数ファイルの多段階探索（外部config・リポジトリ内.env・.env.exampleフォールバック対応）"""
    candidates = [
        os.getenv("ANA_AWARD_ENV_FILE"),
        os.path.abspath(os.path.join(BASE_DIR, "../../../config/ana-award-search.env")),
        os.path.abspath(os.path.join(BASE_DIR, ".env")),
        os.path.abspath(os.path.join(BASE_DIR, "../.env")),
        os.path.abspath(os.path.join(BASE_DIR, "../.env.example")),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            load_dotenv(path)
            return path
    return None


load_app_env()

UA_USER = os.getenv("UA_USERNAME", "")
UA_PW = os.getenv("UA_PASSWORD", "")
ANA_ID = os.getenv("ANA_MEMBER_ID", "")
ANA_PW = os.getenv("ANA_PASSWORD", "")
HOST_API_TOKEN = os.getenv("HOST_API_TOKEN", "ana-award-local-token-2026")
HOST_API_BIND = os.getenv("HOST_API_BIND", "0.0.0.0")
PROFILE_DIR = os.path.join(BASE_DIR, "ua_profile")

ANA_AWARD_INPUT_URL = (
    "https://aswbe-i.ana.co.jp/international_asw/pages/award/search/roundtrip/"
    "award_search_roundtrip_input.xhtml?CONNECTION_KIND=JPN&LANG=ja"
)
DOW_JP = ["月", "火", "水", "木", "金", "土", "日"]

# 画面の外の座標（ここに置くと見えなくなる）
HIDDEN_POS = {"left": -32000, "top": -32000}
# ログイン時に表示する位置とサイズ
VISIBLE_POS = {"left": 100, "top": 50, "width": 1280, "height": 900}

# 画面外でもページの読み込みが止まらないようにするChromeの起動オプション
CHROME_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--window-position=-32000,-32000",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
]

# ---------- 状態 ----------
playwright_instance = None
browser_ctx = None
ana_page = None
search_lock = asyncio.Lock()  # 検索・ログインを同時に1つだけ実行するための鍵


def log(msg: str):
    """ログ出力（ファイルにすぐ書き出されるよう flush する）"""
    print(msg, flush=True)


def search_url(origin: str, destination: str, date_str: str, passengers: int = 1) -> str:
    return (f"https://www.united.com/en/us/fsr/choose-flights?f={origin}&t={destination}&d={date_str}"
            f"&tt=1&at=1&rm=1&act=0&px={passengers}&taxng=1&newHP=True&clm=7&st=bestmatches&fareWheel=False")


# ---------- ブラウザ管理 ----------
async def ensure_browser():
    """Chromeが起動していなければ起動する（閉じられた場合の再起動も兼ねる）"""
    global playwright_instance, browser_ctx
    if browser_ctx is not None:
        return
    if playwright_instance is None:
        playwright_instance = await async_playwright().start()
    log("Chromeを画面外で起動します...")
    ctx = await playwright_instance.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR, channel="chrome", headless=False,
        args=CHROME_ARGS, locale="en-US",
    )

    def on_close(_):
        # ユーザーがChromeを閉じた等で終了した場合、次回の検索で再起動させる
        global browser_ctx
        browser_ctx = None
        log("Chromeが閉じられました（次回の検索時に再起動します）")

    ctx.on("close", on_close)
    browser_ctx = ctx


async def move_window(page, visible: bool):
    """Chromeの窓を閉じずに、画面内 / 画面外へ移動する（Chromeの開発者向け機能 CDP を使用）"""
    try:
        cdp = await page.context.new_cdp_session(page)
        win = await cdp.send("Browser.getWindowForTarget")
        wid = win["windowId"]
        # 最小化・最大化状態だと位置を変えられないため、いったん通常状態に戻す
        await cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "normal"}})
        await cdp.send("Browser.setWindowBounds",
                       {"windowId": wid, "bounds": VISIBLE_POS if visible else HIDDEN_POS})
        await cdp.detach()
        if visible:
            await page.bring_to_front()
    except Exception as e:
        log(f"窓の移動に失敗しました: {e}")


# ---------- ログイン ----------
async def is_visible(locator) -> bool:
    try:
        return await locator.count() > 0 and await locator.first.is_visible()
    except Exception:
        return False


async def needs_login(page) -> bool:
    """検索結果ページにログイン要求や確認コード（2段階認証）入力画面が出ているか判定"""
    try:
        url_low = (page.url or "").lower()
        if any(k in url_low for k in ("login", "signin", "auth", "verify")):
            return True

        return await page.evaluate(
            """() => {
                const isVis = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };

                // 1. パスワード入力欄が表示されている
                if (isVis(document.querySelector('input#password, input[type="password"]'))) return true;

                // 2. ワンタイムコード・確認コード入力欄が表示されている
                const codeInputs = document.querySelectorAll(
                    'input[autocomplete="one-time-code"], input[name*="code" i], input[id*="code" i], input[name*="otp" i], input[id*="otp" i], input[name*=" answer" i], input[id*="answer" i]'
                );
                for (const inp of codeInputs) {
                    if (isVis(inp)) return true;
                }

                // 3. モーダルダイアログ（ログイン・本人確認・コード入力・セキュリティ質問）が開いている
                const dialogs = document.querySelectorAll('[role="dialog"], [aria-modal="true"]');
                for (const dlg of dialogs) {
                    if (!isVis(dlg)) continue;
                    const txt = (dlg.innerText || '').toLowerCase();
                    if (
                        txt.includes('sign in') ||
                        txt.includes('verify') ||
                        txt.includes('verification') ||
                        txt.includes('code') ||
                        txt.includes('security') ||
                        txt.includes('authenticate') ||
                        txt.includes('confirm your identity') ||
                        txt.includes('signed-in to see flight results')
                    ) {
                        return true;
                    }
                }

                // 4. 未ログイン警告または確認コード要求テキストが表示されている
                const bodyTxt = (document.body ? document.body.innerText : '').toLowerCase();
                if (
                    bodyTxt.includes('signed-in to see flight results with miles') ||
                    bodyTxt.includes('sign in for the best experience') ||
                    bodyTxt.includes('verify your identity') ||
                    bodyTxt.includes('verification code') ||
                    bodyTxt.includes('enter the code') ||
                    bodyTxt.includes('we sent a code') ||
                    bodyTxt.includes('security code')
                ) {
                    return true;
                }

                return false;
            }"""
        )
    except Exception:
        return True


async def is_fully_logged_in(page) -> bool:
    """コード手打ち・ログインが完全に完了し、マイル付きのフライト結果画面が表示されたか厳密に判定"""
    if await needs_login(page):
        return False
    try:
        return await page.evaluate(
            """() => {
                const bodyTxt = (document.body ? document.body.innerText : '');
                // フライト結果一覧（Details for the flight）かつマイル表示（k miles）が実際に画面に出ていることだけを完了条件とする
                const hasFlights = document.querySelectorAll('[aria-label*="Details for the flight"]').length > 0;
                const hasMiles = /\\d+(\\.\\d+)?k\\s*miles/i.test(bodyTxt) || (bodyTxt.includes('miles') && !bodyTxt.includes('signed-in to see flight results with miles'));
                return Boolean(hasFlights && hasMiles);
            }"""
        )
    except Exception:
        return False


def show_message(text: str, title: str):
    """Windowsのダイアログを最前面に表示（OKが押されるまで待つ）"""
    ctypes.windll.user32.MessageBoxW(0, text, title, 0x40 | 0x10000 | 0x40000)


async def fill_login_credentials(page, username: str, password: str) -> bool:
    """ログイン画面の入力欄（ユーザー名/メールアドレスおよびパスワード）を判定して自動入力する（指示08対応）"""
    entered = False

    # 1. サインインパネルを開くボタンがある場合はクリック
    sign_in_btn = page.get_by_role("button", name="Sign In", exact=True)
    pw_input = page.locator('input#password, input[type="password"]')
    user_input = page.locator(
        'input#username, input#email, input#mileagePlusNumber, input[name*="username" i], input[name*="email" i], input[name*="mileage" i], input[autocomplete="username"], input[type="email"]'
    )

    if not await is_visible(pw_input) and not await is_visible(user_input) and await is_visible(sign_in_btn):
        await sign_in_btn.first.click()
        await asyncio.sleep(3)

    # 2. ユーザー名 / MileagePlus番号 / メールアドレスの入力
    user_input = page.locator(
        'input#username, input#email, input#mileagePlusNumber, input[name*="username" i], input[name*="email" i], input[name*="mileage" i], input[autocomplete="username"], input[type="email"]'
    )
    if username and await is_visible(user_input):
        try:
            log("ユーザー名/MileagePlus番号を入力します...")
            await user_input.first.fill(username)
            entered = True
            await asyncio.sleep(0.5)

            # ステップ型ログイン（ユーザー名入力後に次へボタンを押す画面）の場合
            pw_input = page.locator('input#password, input[type="password"]')
            if not await is_visible(pw_input):
                next_btn = page.locator(
                    'button[type="submit"], button:has-text("Continue"), button:has-text("Next"), button:has-text("Sign in"), button:has-text("Sign In")'
                )
                if await is_visible(next_btn):
                    await next_btn.first.click()
                    await asyncio.sleep(3)
        except Exception as e:
            log(f"ユーザー名入力中にエラー: {e}")

    # 3. パスワードの入力
    pw_input = page.locator('input#password, input[type="password"]')
    if password and await is_visible(pw_input):
        try:
            log("パスワードを入力します...")
            await pw_input.first.fill(password)
            entered = True
            submit = page.locator('button[type="submit"]', has_text=re.compile(r"^\s*Sign in\s*$", re.IGNORECASE))
            if await is_visible(submit):
                await submit.first.click()
                log("パスワードを送信しました。画面の切り替わりを待機します...")
                await asyncio.sleep(8)
            else:
                submit_alt = page.locator('button:has-text("Sign in"), button:has-text("Sign In")')
                if await is_visible(submit_alt):
                    await submit_alt.first.click()
                    await asyncio.sleep(8)
        except Exception as e:
            log(f"パスワード入力中にエラー: {e}")

    return entered


async def do_login(page):
    """ログインが必要なページで、ユーザー名・パスワード自動入力 → コード入力画面で一時停止し、ログイン完了を確認して再開"""
    log("ログインが必要です。Chromeを最前面に表示して自動ログインを試みます...")
    await bring_window_to_foreground(page)
    await fill_login_credentials(page, UA_USER, UA_PW)

    # すでに完全ログイン済みか確認し、コード入力画面等が出ている場合は手打ち完了まで完全停止して待つ
    log("確認コード入力またはログイン完了の確認を待機しています（手打ち完了後に自動再開します）...")
    logged_in_confirmed = False
    # 最長5分（2秒×150回）待機
    for _ in range(150):
        if await is_fully_logged_in(page):
            # 画面遷移の一瞬の隙を誤検知しないよう、4秒待ってもう一度ログイン完了を確認する
            await asyncio.sleep(4)
            if await is_fully_logged_in(page):
                log("ログインの完了を完全に確認しました！処理を再開します。")
                logged_in_confirmed = True
                break
        await asyncio.sleep(2)

    if not logged_in_confirmed:
        log("ログイン待機時間がタイムアウトしました。")
    return logged_in_confirmed


async def initial_login_check():
    """起動直後にログイン状態を確認しておく（必要ならこの時点でログイン）"""
    async with search_lock:
        page = None
        try:
            await ensure_browser()
            page = await browser_ctx.new_page()
            await move_window(page, visible=True)  # 強制的に画面内へ引き戻す
            check_date = (date.today() + timedelta(days=30)).isoformat()
            await page.goto(search_url("HND", "HNL", check_date), wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(15)
            if await needs_login(page):
                await do_login(page)
            else:
                log("ログイン済みです")
        except Exception:
            log("起動時のログイン確認でエラー:\n" + traceback.format_exc())
        finally:
            if page:
                await page.close()
        log("準備完了：検索を受け付けます")


# ---------- 検索結果の読み取り ----------
def parse_flights_with_meta(html):
    """HTMLからフライト情報を抽出する（運賃クラス保持およびパース失敗検知）"""
    soup = BeautifulSoup(html, "html.parser")
    flight_nodes = soup.find_all(lambda tag: tag.has_attr("aria-label") and "Details for the flight" in tag["aria-label"])

    results = []
    failed_count = 0
    for node in flight_nodes:
        flight_desc = node.get("aria-label", "")
        parent = node
        for _ in range(6):
            if parent.parent and parent.parent.name not in ["body", "html"]:
                # 祖先を遡りすぎて他のフライトブロックを巻き込まないようにする
                other_flights = parent.parent.find_all(lambda tag: tag.has_attr("aria-label") and "Details for the flight" in tag["aria-label"])
                if len(other_flights) > 1:
                    break
                parent = parent.parent
            else:
                break
        raw_text = parent.get_text(separator=" | ", strip=True)

        eco_match = re.search(r"Economy(?:\s*\(([A-Za-z0-9]+)\))?\s*\|\s*([\d\.]+k)\s*\|\s*miles", raw_text, re.IGNORECASE)
        bus_match = re.search(r"Business(?:\s*\(([A-Za-z0-9]+)\))?\s*\|\s*([\d\.]+k)\s*\|\s*miles", raw_text, re.IGNORECASE)
        first_match = re.search(r"First(?:\s*\(([A-Za-z0-9]+)\))?\s*\|\s*([\d\.]+k)\s*\|\s*miles", raw_text, re.IGNORECASE)

        # マイルまたは価格表記が全く取れず、クラス抽出が空の場合はパース失敗カードとしてカウント
        if not eco_match and not bus_match and not first_match:
            failed_count += 1
            results.append({
                "flight_description": flight_desc,
                "economy_miles": "N/A",
                "economy_fare_class": None,
                "business_miles": "N/A",
                "business_fare_class": None,
                "first_miles": "N/A",
                "first_fare_class": None,
                "parse_failed": True,
            })
            continue

        eco_miles = eco_match.group(2) if eco_match else "N/A"
        eco_class = eco_match.group(1).upper() if (eco_match and eco_match.group(1)) else ("UNKNOWN" if eco_match else None)

        bus_miles = bus_match.group(2) if bus_match else "N/A"
        bus_class = bus_match.group(1).upper() if (bus_match and bus_match.group(1)) else ("UNKNOWN" if bus_match else None)

        first_miles = first_match.group(2) if first_match else "N/A"
        first_class = first_match.group(1).upper() if (first_match and first_match.group(1)) else ("UNKNOWN" if first_match else None)

        results.append({
            "flight_description": flight_desc,
            "economy_miles": eco_miles,
            "economy_fare_class": eco_class,
            "business_miles": bus_miles,
            "business_fare_class": bus_class,
            "first_miles": first_miles,
            "first_fare_class": first_class,
            "parse_failed": False,
        })
    return results, failed_count


def parse_flights(html):
    """下位互換用: フライトリストのみを返す"""
    flights, _ = parse_flights_with_meta(html)
    return flights


def check_display_mode(html: str) -> str:
    """HTMLから検索結果の表示モード（'miles', 'cash', 'no_flights'）を判定する"""
    soup = BeautifulSoup(html, "html.parser")
    flight_nodes = soup.find_all(lambda tag: tag.has_attr("aria-label") and "Details for the flight" in tag["aria-label"])
    if not flight_nodes:
        return "no_flights"

    all_cards_text = []
    for node in flight_nodes:
        parent = node
        for _ in range(6):
            if parent.parent and parent.parent.name not in ["body", "html"]:
                other_flights = parent.parent.find_all(lambda tag: tag.has_attr("aria-label") and "Details for the flight" in tag["aria-label"])
                if len(other_flights) > 1:
                    break
                parent = parent.parent
            else:
                break
        all_cards_text.append(parent.get_text(separator=" | ", strip=True))

    full_cards_text = " ".join(all_cards_text)
    has_miles = bool(re.search(r"miles\b", full_cards_text, re.IGNORECASE))
    has_cash = bool(re.search(r"(\$|USD|JPY|EUR)\s*[\d,]+", full_cards_text, re.IGNORECASE))

    if not has_miles and has_cash:
        return "cash"
    return "miles"


def check_rate_limit(html: str) -> bool:
    """HTML内にユナイテッド航空の一時制限画面（We're sorry...）が含まれているか判定（指示07対応）"""
    return "we're sorry, but united.com was unable to complete your request" in html.lower()


# ---------- API ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時：Chromeのみ待機状態で起動（勝手なダミー検索・ログイン試行は行わない）
    await ensure_browser()
    log("準備完了：検索を受け付けます")
    yield
    # 終了時：Chromeを閉じる
    log("終了します...")
    if browser_ctx:
        await browser_ctx.close()
    if playwright_instance:
        await playwright_instance.stop()


app = FastAPI(title="UA Scraper API", lifespan=lifespan)


@app.middleware("http")
async def verify_token_middleware(request: Request, call_next):
    """ホストAPI認証ミドルウェア: X-Host-Token を照合し、LAN等からの不正アクセスを遮断（指示06対応）"""
    if request.url.path.startswith("/api/"):
        token = request.headers.get("X-Host-Token")
        if token != HOST_API_TOKEN:
            client_ip = request.client.host if request.client else "unknown"
            log(f"【セキュリティ】認証なしまたは不正トークンのアクセスを拒否しました: IP={client_ip}, path={request.url.path}")
            return JSONResponse(
                status_code=401,
                content={"detail": "認証トークンが無効または未指定です。アクセスが拒否されました。"},
            )
    return await call_next(request)


@app.get("/api/search")
async def search_flights(origin: str, destination: str, date: str, passengers: int = 1):
    log(f"検索リクエスト: {origin} -> {destination} {date} ({passengers}名)")
    async with search_lock:
        # 1回目でログイン切れが分かったら、そのタブでログイン完了まで待機する
        for attempt in range(2):
            page = None
            keep_open_on_exit = False
            try:
                await ensure_browser()
                page = await browser_ctx.new_page()
                await move_window(page, visible=True)  # 強制的に画面内へ引き戻す
                await page.goto(search_url(origin, destination, date, passengers), wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(15)

                # Escapeでポップアップを閉じる前に、ログイン切れかどうかを確認する
                if await needs_login(page):
                    if attempt == 0:
                        ok = await do_login(page)
                        if not ok:
                            # 時間が過ぎてもコード入力が完了しなかった場合は、タブを閉じずにそのまま残し、401で即時中断させる（再試行しない）
                            keep_open_on_exit = True
                            raise HTTPException(
                                status_code=401,
                                detail="認証コードの入力待機時間を過ぎたため、作業を停止しました（再度のログイン試行は行いません）。",
                            )
                        # ログイン・コード手打ち完了後、同じタブにフライト結果が出ていればタブを閉じずにそのまま読み取る
                        if not await is_fully_logged_in(page):
                            continue
                    else:
                        keep_open_on_exit = True
                        raise HTTPException(
                            status_code=401,
                            detail="ユナイテッド航空のログインが完了していないため、作業を停止しました。",
                        )

                # ユナイテッド航空の一時エラー画面（We're sorry...）の検知（指示07対応: 空席なしと誤認させず429を送出）
                sorry_banner = page.locator("text=We're sorry, but united.com was unable to complete your request")
                if await is_visible(sorry_banner):
                    log(f"【検知】{origin}->{destination} ({date}) でユナイテッド航空の一時エラー画面（We're sorry...）が表示されました")
                    raise HTTPException(
                        status_code=429,
                        detail="ユナイテッド航空の一時アクセス制限（We're sorry画面）を検知しました。",
                    )

                await page.keyboard.press("Escape")
                await asyncio.sleep(2)
                try:
                    await page.wait_for_selector('[aria-label*="Details for the flight"]', timeout=30000)
                except Exception:
                    log("便が表示されませんでした（該当便なしの可能性）")

                await asyncio.sleep(2)
                html = await page.content()
                # 調査用に最新の画面写真を1枚だけ残す（毎回上書き）
                await page.screenshot(path=os.path.join(BASE_DIR, "api_debug_resident.png"), full_page=True)

                if check_rate_limit(html):
                    log(f"【検知】{origin}->{destination} ({date}) HTML内で一時エラー画面（We're sorry...）を検知しました")
                    raise HTTPException(
                        status_code=429,
                        detail="ユナイテッド航空の一時アクセス制限（We're sorry画面）を検知しました。",
                    )

                # 現金表示モードの検知（指示03）
                display_mode = check_display_mode(html)
                if display_mode == "cash":
                    log("【検知】検索結果が現金表示（通貨）になっています。マイル表示への切替が必要です。")
                    raise HTTPException(
                        status_code=409,
                        detail="ユナイテッド航空の検索結果が現金表示になっています。マイル表示への切替が必要です。",
                    )

                flights, parse_failed_count = parse_flights_with_meta(html)
                log(f"{len(flights)} 便抽出完了（パース失敗: {parse_failed_count} 便）")
                return {
                    "status": "success",
                    "flights": flights,
                    "parse_failed_count": parse_failed_count,
                }

            except HTTPException:
                raise
            except Exception as e:
                log("検索中にエラー:\n" + traceback.format_exc())
                raise HTTPException(status_code=500, detail=str(e))
            finally:
                if page and not page.is_closed() and not keep_open_on_exit:
                    await page.close()


class AnaAutofillRequest(BaseModel):
    origin: str
    destination: str
    date: str
    cabin: str = "economy"
    passengers: int = 1


async def bring_window_to_foreground(page):
    """Windows上でChromeウィンドウを確実に最前面（フォアグラウンド）へ引き올げる"""
    try:
        cdp = await page.context.new_cdp_session(page)
        win = await cdp.send("Browser.getWindowForTarget")
        wid = win["windowId"]
        # 一瞬最小化してから通常サイズに戻すことでWindowsの前面フォーカス制限を突破する
        await cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "minimized"}})
        await asyncio.sleep(0.15)
        await cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "normal"}})
        await cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": VISIBLE_POS})
        await cdp.detach()
        await page.bring_to_front()
    except Exception as e:
        log(f"ウィンドウ前面化エラー: {e}")


async def _run_ana_autofill(page, req: AnaAutofillRequest):
    """ANA国際線特典航空券ページへ遷移し、必要なら自動ログインして検索条件を自動入力する"""
    try:
        dep_d = date.fromisoformat(req.date)
        ret_d = dep_d + timedelta(days=7)
        if (ret_d - date.today()).days > 354:
            ret_d = dep_d + timedelta(days=1) if (dep_d - date.today()).days < 354 else dep_d

        dep_hidden = dep_d.strftime("%Y%m%d")
        dep_disp = f"{dep_d.year}年{dep_d.month:02d}月{dep_d.day:02d}日({DOW_JP[dep_d.weekday()]})"
        ret_hidden = ret_d.strftime("%Y%m%d")
        ret_disp = f"{ret_d.year}年{ret_d.month:02d}月{ret_d.day:02d}日({DOW_JP[ret_d.weekday()]})"

        log(f"ANA特典予約画面を開きます: {req.origin} -> {req.destination} ({req.date})")
        await page.goto(ANA_AWARD_INPUT_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)

        # 未ログインでログイン画面に遷移した場合は自動ログインを実行
        if "login" in page.url.lower() or await is_visible(page.locator("input#accountNumber")):
            log("ANAログイン画面を検知しました。ID/パスワードを入力します...")
            if ANA_ID and ANA_PW:
                try:
                    await page.fill("input#accountNumber", ANA_ID)
                    await page.fill("input#password", ANA_PW)
                    await page.click("input#amcMemberLogin", force=True)
                    log("ANAログイン送信完了。コード入力画面が出た場合は手打ち完了まで待機します...")
                    await asyncio.sleep(3)
                except Exception as e:
                    log(f"ANA自動ログイン入力エラー: {e}")

        # コード入力（ワンタイムパスワード等）が必要な場合は手打ちして検索フォームが表示されるまで最大5分（300秒）待機
        await page.wait_for_selector("input[name='departureAirportCode:field_pctext']", state="visible", timeout=300000)
        await asyncio.sleep(2.0)
        await page.bring_to_front()

        # 出発地・到着地のテキスト欄に入力してサジェストまたはTab確定を試みる
        try:
            dep_input = page.locator("input[name='departureAirportCode:field_pctext']")
            await dep_input.click()
            await dep_input.fill(req.origin)
            await asyncio.sleep(0.5)
            await page.keyboard.press("Tab")

            arr_input = page.locator("input[name='arrivalAirportCode:field_pctext']")
            await arr_input.click()
            await arr_input.fill(req.destination)
            await asyncio.sleep(0.5)
            await page.keyboard.press("Tab")
        except Exception as e:
            log(f"空港テキスト入力補助エラー: {e}")

        # JavaScriptで隠しフィールド・日付・クラス・人数を確実にセットする
        await page.evaluate(
            """(p) => {
                const setVal = (sel, val) => {
                    const el = document.querySelector(sel);
                    if (el) {
                        el.removeAttribute('readonly');
                        el.value = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                };

                // 出発地・到着地の隠しコードと表示テキスト
                setVal("input[name='departureAirportCode:field']", p.origin);
                const depTxt = document.querySelector("input[name='departureAirportCode:field_pctext']");
                if (depTxt && !depTxt.value) setVal("input[name='departureAirportCode:field_pctext']", p.origin);

                setVal("input[name='arrivalAirportCode:field']", p.dest);
                const arrTxt = document.querySelector("input[name='arrivalAirportCode:field_pctext']");
                if (arrTxt && !arrTxt.value) setVal("input[name='arrivalAirportCode:field_pctext']", p.dest);

                // 往路出発日・復路出発日（仮で7日後）
                setVal("input[name='awardDepartureDate:field']", p.depHidden);
                setVal("input[name='awardDepartureDate:field_pctext']", p.depDisp);
                setVal("input[name='awardReturnDate:field']", p.retHidden);
                setVal("input[name='awardReturnDate:field_pctext']", p.retDisp);

                // 搭乗クラス選択
                const clsSel = document.querySelector("select#boardingClass, select[name='boardingClass']");
                if (clsSel) {
                    const kw = p.cabin === 'first' ? 'ファースト' : (p.cabin === 'business' ? 'ビジネス' : 'エコノミー');
                    for (const opt of clsSel.options) {
                        if (opt.text.includes(kw)) {
                            clsSel.value = opt.value;
                            clsSel.dispatchEvent(new Event('change', { bubbles: true }));
                            break;
                        }
                    }
                }

                // 大人人数選択
                const paxSel = document.querySelector("select[name='adult:count']");
                if (paxSel) {
                    paxSel.value = p.passengers;
                    paxSel.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }""",
            {
                "origin": req.origin,
                "dest": req.destination,
                "depHidden": dep_hidden,
                "depDisp": dep_disp,
                "retHidden": ret_hidden,
                "retDisp": ret_disp,
                "cabin": req.cabin,
                "passengers": str(req.passengers),
            },
        )
        log(f"ANA特典検索フォームへの自動入力が完了しました: {req.origin} -> {req.destination} ({req.date})")
    except Exception:
        log("ANA自動入力処理中にエラー:\n" + traceback.format_exc())


@app.post("/api/ana-autofill")
async def ana_autofill(req: AnaAutofillRequest):
    """新しいタブでANA国際線特典予約画面を開き、検索条件を自動入力する"""
    global ana_page
    try:
        await ensure_browser()
        if ana_page and not ana_page.is_closed():
            try:
                await ana_page.close()
            except Exception:
                pass
        ana_page = await browser_ctx.new_page()
        await bring_window_to_foreground(ana_page)
        asyncio.create_task(_run_ana_autofill(ana_page, req))
        return {"status": "started"}
    except Exception as e:
        log("ANA自動入力起動エラー:\n" + traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST_API_BIND, port=8001)
