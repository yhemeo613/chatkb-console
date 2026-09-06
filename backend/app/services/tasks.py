# -*- coding: utf-8 -*-
"""
后台任务系统：线程池执行 + Redis 持久化任务状态 + Pub/Sub 实时推送。

任务状态写入 Redis（chatkb:task:{id}），后端重启不丢失历史；
每次进度变化 publish 到 chatkb:tasks 频道，供 WebSocket 转发给前端。
"""
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import cache

_executor = ThreadPoolExecutor(max_workers=2)
_local: dict[str, dict] = {}
_lock = threading.Lock()

CHANNEL = "tasks"
FINISHED_TTL = 24 * 3600


def _save(task: dict):
    cache.set_json(f"task:{task['id']}", task,
                   ttl=FINISHED_TTL if task["status"] != "running" else None)


def submit(name: str, total: int, fn) -> str:
    task_id = uuid.uuid4().hex[:12]
    task = {
        "id": task_id, "name": name, "status": "running",
        "total": total, "done": 0, "message": "", "log": [],
        "created_at": time.time(), "finished_at": None, "error": "",
    }
    with _lock:
        _local[task_id] = task
    _save(task)

    def cb(increment: int = 1, message: str = ""):
        with _lock:
            t = _local[task_id]
            t["done"] = min(t["total"], t["done"] + increment)
            if message:
                t["message"] = message
                t["log"].append(message)
                if len(t["log"]) > 200:
                    del t["log"][:100]
            snapshot = dict(t)
        _save(snapshot)
        cache.publish(CHANNEL, {"event": "progress", **{
            k: snapshot[k] for k in ("id", "status", "done", "total", "message")}})

    def run():
        try:
            fn(cb)
            with _lock:
                t = _local[task_id]
                t["status"], t["finished_at"] = "success", time.time()
                snapshot = dict(t)
        except Exception as e:
            with _lock:
                t = _local[task_id]
                t["status"], t["error"], t["finished_at"] = "failed", str(e), time.time()
                t["log"].append(f"[错误] {e}")
                snapshot = dict(t)
        _save(snapshot)
        cache.publish(CHANNEL, {"event": "progress", **{
            k: snapshot[k] for k in ("id", "status", "done", "total", "message")}})
        # 释放内存引用（状态已持久化在 Redis）
        with _lock:
            _local.pop(task_id, None)

    _executor.submit(run)
    return task_id


def get(task_id: str) -> dict | None:
    with _lock:
        if task_id in _local:
            return dict(_local[task_id])
    return cache.get_json(f"task:{task_id}")


def running_count() -> int:
    return sum(1 for t in list(_local.values()) if t["status"] == "running")


def recent(limit: int = 10) -> list[dict]:
    with _lock:
        running = [dict(t) for t in _local.values()]
    done_ids = [k[len(cache.PREFIX) + 5:] for k in cache.get_client().scan_iter(cache.PREFIX + "task:*", count=100)]
    done = [t for t in (cache.get_json(f"task:{i}") for i in done_ids) if t and t["id"] not in {r["id"] for r in running}]
    return sorted(running + done, key=lambda x: x["created_at"], reverse=True)[:limit]


def cleanup_finished(max_age_hours: int = 48) -> int:
    """定时任务：清理超过 max_age 的历史任务（由 APScheduler 调用）"""
    n = 0
    now_ts = time.time()
    for k in cache.get_client().scan_iter(cache.PREFIX + "task:*", count=100):
        t = cache.get_json(k[len(cache.PREFIX):])
        if t and t["status"] != "running" and t.get("finished_at") and now_ts - t["finished_at"] > max_age_hours * 3600:
            cache.get_client().delete(k)
            n += 1
    return n
