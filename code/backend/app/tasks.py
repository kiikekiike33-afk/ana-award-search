import random
import time
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor

from celery import Celery

from .areas import build_queries
from .config import settings
from .progress import JobStore
from .scraper import get_provider
from .scraper.base import BlockedError, CashDisplayError, RateLimitError, RetryableError, SessionExpiredError

celery_app = Celery("ana", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(worker_prefetch_multiplier=1, task_acks_late=True)


def polite_sleep(i: int) -> None:
    if settings.scraper_provider == "mock":
        time.sleep(0.3)
        return
    time.sleep(random.uniform(settings.min_delay_sec, settings.max_delay_sec))
    if i % settings.long_break_every == 0:
        time.sleep(settings.long_break_sec * random.uniform(0.8, 1.2))


def search_with_retry(provider, q: dict):
    for attempt in range(1, settings.max_retries + 1):
        try:
            return provider.search(q)
        except BlockedError:
            # 認証コード待機などで作業を止める場合は、リトライせず即座に中断する
            raise
        except (CashDisplayError, RateLimitError):
            # 現金表示やWe're sorry一時制限は即座に上位へ伝え、エラー通知・スキップ処理する
            raise
        except SessionExpiredError:
            if attempt == settings.max_retries:
                raise
            provider.relogin()
        except RetryableError:
            if attempt == settings.max_retries:
                raise
        time.sleep((2 ** attempt) * 5 + random.uniform(0, 3))


def _run_queries_in_thread(job_id: str, queries: list, total: int, started: float):
    store = JobStore(settings.redis_url)
    consecutive_rate_limits = 0
    MAX_CONSECUTIVE_RATE_LIMITS = 3

    try:
        with get_provider() as provider:
            for i, q in enumerate(queries, 1):
                if store.is_cancelled(job_id):
                    store.update(job_id, status="cancelled")
                    store.publish(job_id, {"type": "cancelled"})
                    return

                label = f"{q['origin']} => {q['destination']} {q['date']}"
                elapsed = time.time() - started
                eta = int(elapsed / (i - 1) * (total - i + 1)) if i > 1 else None
                store.update(job_id, done=i - 1, current=label, eta_sec=eta or "")
                store.publish(job_id, {"type": "progress", "done": i - 1, "total": total,
                                       "current": label, "eta_sec": eta})
                try:
                    res = search_with_retry(provider, q)
                    consecutive_rate_limits = 0  # 正常取得できたら連続制限カウントをリセット
                    if res.available:
                        data = asdict(res)
                        store.add_result(job_id, data)
                        store.publish(job_id, {"type": "result", "result": data})
                except BlockedError:
                    raise
                except RateLimitError as e:
                    consecutive_rate_limits += 1
                    msg = f"一時制限検知(We're sorry) [{consecutive_rate_limits}/{MAX_CONSECUTIVE_RATE_LIMITS}]: 空席なしと記録せずスキップします"
                    store.publish(job_id, {"type": "error", "current": label, "message": msg})
                    if consecutive_rate_limits >= MAX_CONSECUTIVE_RATE_LIMITS:
                        raise BlockedError("ユナイテッド航空の一時アクセス制限（We're sorry画面）が3回連続したため、アカウント保護のため検索ジョブを自動停止しました。")
                    time.sleep(15)  # 単発の一時制限時は15秒クールダウンして次へ
                except Exception as e:
                    store.publish(job_id, {"type": "error", "current": label, "message": repr(e)})
                polite_sleep(i)

        store.update(job_id, status="done", done=total, current="")
        store.publish(job_id, {"type": "done", "done": total, "total": total})
    except Exception as e:
        import traceback
        traceback.print_exc()
        store.update(job_id, status="failed")
        store.publish(job_id, {"type": "failed", "message": repr(e)})


@celery_app.task(bind=True)
def run_search(self, job_id: str, params: dict) -> None:
    store = JobStore(settings.redis_url)
    queries = build_queries(params)
    total, started = len(queries), time.time()
    store.update(job_id, status="running")

    if total == 0:
        store.update(job_id, status="done", done=0, current="")
        store.publish(job_id, {"type": "done", "done": 0, "total": 0})
        return

    # Playwrightの非同期イベントループ競合を避けるため、別スレッドでブラウザ操作を実行する
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_queries_in_thread, job_id, queries, total, started)
        future.result()  # スレッド内の例外もここで伝播する（ただし関数内でキャッチ済み）
