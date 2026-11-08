"""検索ごとの状態・結果をRedisに保存し、進捗を通知する。"""
import json
import time

import redis

TTL = 60 * 60 * 24   # 24時間で自動削除


def k(job_id: str, s: str) -> str:
    """Redisのキー名を作る。"""
    return f"job:{job_id}:{s}"


class JobStore:
    def __init__(self, url: str):
        self.r = redis.Redis.from_url(url, decode_responses=True)

    def create(self, job_id: str, params: dict, total: int) -> None:
        self.r.hset(k(job_id, "meta"), mapping={
            "status": "queued", "done": 0, "total": total, "current": "",
            "eta_sec": "", "params": json.dumps(params), "created_at": time.time()})
        self.r.expire(k(job_id, "meta"), TTL)

    def update(self, job_id: str, **fields) -> None:
        self.r.hset(k(job_id, "meta"), mapping={a: str(b) for a, b in fields.items()})

    def publish(self, job_id: str, event: dict) -> None:
        self.r.publish(k(job_id, "events"), json.dumps(event, ensure_ascii=False))

    def add_result(self, job_id: str, result: dict) -> None:
        self.r.rpush(k(job_id, "results"), json.dumps(result, ensure_ascii=False))
        self.r.expire(k(job_id, "results"), TTL)

    def cancel(self, job_id: str) -> None:
        self.r.set(k(job_id, "cancel"), 1, ex=TTL)

    def is_cancelled(self, job_id: str) -> bool:
        return self.r.exists(k(job_id, "cancel")) == 1

    def cancel_all_active(self) -> None:
        """実行中または待機中の既存ジョブをすべてキャンセル状態にする"""
        for meta_key in self.r.keys("job:*:meta"):
            status = self.r.hget(meta_key, "status")
            if status in ("running", "queued"):
                job_id = meta_key.split(":")[1]
                self.cancel(job_id)
                self.update(job_id, status="cancelled")
                self.publish(job_id, {"type": "cancelled"})
