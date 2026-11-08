"""FastAPI：検索の受付、状態の取得、SSEでの進捗配信、キャンセル、ANA自動入力中継。"""
import json
import urllib.error
import urllib.request
import uuid
from datetime import date
from typing import Literal

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from .areas import AIRPORT_NAMES, AREAS, ORIGINS, build_queries
from .config import settings
from .progress import JobStore, k
from .routes import DIRECT_FLIGHTS
from .tasks import celery_app, run_search

app = FastAPI(title="ANA特典航空券 空席サーチ")
store = JobStore(settings.redis_url)
TERMINAL = {"done", "failed", "cancelled"}

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [err["msg"].replace("Value error, ", "") for err in exc.errors()]
    return JSONResponse(status_code=400, content={"detail": errors})

class SearchRequest(BaseModel):
    origin: str = "TYO"
    destination: str                 # エリア名（例：europe）または空港コード
    start_date: date
    end_date: date
    cabin: Literal["economy", "business", "first"]
    passengers: int = Field(1, ge=1, le=9)
    direct_only: bool = True         # 直行便がある路線のみ検索（無駄な検索を省く）

    @model_validator(mode="after")
    def check_range(self):
        if self.end_date < self.start_date:
            raise ValueError("終了日は開始日以降にしてください")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("検索期間は1年以内にしてください")
        return self


@app.get("/api/areas")
def areas():
    """出発地・目的地エリア・空港名・直行便ルートのマスタ情報を返す"""
    return {
        "origins": ORIGINS,
        "areas": AREAS,
        "airport_names": AIRPORT_NAMES,
        "direct_flights": DIRECT_FLIGHTS,
    }


@app.post("/api/searches", status_code=202)
def create_search(req: SearchRequest):
    params = req.model_dump(mode="json")
    try:
        total = len(build_queries(params))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if total > settings.max_queries_per_job:
        raise HTTPException(400, f"検索件数が{total}件で、上限（{settings.max_queries_per_job}件）を超えています。期間かエリアを絞ってください。")

    # 新しい検索を開始する前に、古い未完了ジョブを自動でキャンセル＆キューから破棄
    try:
        store.cancel_all_active()
        celery_app.control.purge()
    except Exception as e:
        print(f"古いジョブの自動破棄中にエラー: {e}")

    job_id = uuid.uuid4().hex
    store.create(job_id, params, total)
    run_search.delay(job_id, params)        # すぐに返す（重い処理はワーカーに任せる）
    return {"job_id": job_id, "total": total}


async def load_snapshot(r, job_id: str):
    """現在の状態と、これまでの結果をまとめて返す。"""
    meta = await r.hgetall(k(job_id, "meta"))
    if not meta:
        return None
    results = [json.loads(x) for x in await r.lrange(k(job_id, "results"), 0, -1)]
    return {"job_id": job_id, "status": meta["status"], "done": int(meta["done"]),
            "total": int(meta["total"]), "current": meta.get("current", ""),
            "eta_sec": int(meta["eta_sec"]) if meta.get("eta_sec") else None,
            "results": results}


@app.get("/api/searches/{job_id}")
async def get_search(job_id: str):
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        snap = await load_snapshot(r, job_id)
    finally:
        await r.aclose()
    if not snap:
        raise HTTPException(404, "指定された検索が見つかりません")
    return snap


@app.post("/api/searches/{job_id}/cancel")
def cancel_search(job_id: str):
    store.cancel(job_id)
    return {"ok": True}


class AnaAutofillPayload(BaseModel):
    origin: str
    destination: str
    date: str
    cabin: str = "economy"
    passengers: int = 1


@app.post("/api/ana-autofill")
def ana_autofill(payload: AnaAutofillPayload):
    """Windowsホスト側のChromeでANA国際線特典予約画面を開き、検索条件を自動入力する"""
    url = "http://host.docker.internal:8001/api/ana-autofill"
    body_bytes = json.dumps(payload.model_dump()).encode("utf-8")
    token = getattr(settings, "host_api_token", "ana-award-local-token-2026")
    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "AnaAwardSearchAPI/1.0",
            "X-Host-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ANA自動入力の呼び出しに失敗しました: {e}")


@app.get("/api/searches/{job_id}/events")
async def search_events(job_id: str, request: Request):
    async def stream():
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(k(job_id, "events"))   # 先に通知の受信を始めてから現状を送る（取りこぼし防止）
        try:
            snap = await load_snapshot(r, job_id)
            if not snap:
                yield f"event: failed\ndata: {json.dumps({'message': '指定された検索が見つかりません'}, ensure_ascii=False)}\n\n"
                return
            yield f"event: snapshot\ndata: {json.dumps(snap, ensure_ascii=False)}\n\n"
            if snap["status"] in TERMINAL:
                return
            while not await request.is_disconnected():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if msg is None:
                    yield ": keepalive\n\n"              # 途中の機器に接続を切られないようにする
                    continue
                ev = json.loads(msg["data"])
                yield f"event: {ev['type']}\ndata: {msg['data']}\n\n"
                if ev["type"] in TERMINAL:
                    break
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()
            await r.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.mount("/", StaticFiles(directory="/srv/frontend", html=True), name="frontend")
