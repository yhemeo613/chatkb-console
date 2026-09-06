# -*- coding: utf-8 -*-
"""WebSocket：任务进度实时推送（Redis Pub/Sub -> 浏览器）"""
import asyncio
import json
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services import cache
from ..services.security import user_from_token

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/tasks/{task_id}")
async def task_progress(ws: WebSocket, task_id: str):
    token = ws.query_params.get("token", "")
    if not user_from_token(token):
        await ws.close(code=4401)
        return

    await ws.accept()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    pubsub = cache.subscribe("tasks")

    def pump():
        """后台线程：阻塞式订阅 Redis，跨线程投递到 asyncio 队列"""
        for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            data = msg.get("data")
            try:
                payload = json.loads(data)
            except Exception:
                continue
            if payload.get("id") != task_id:
                continue
            loop.call_soon_threadsafe(queue.put_nowait, payload)
            if payload.get("status") in ("success", "failed"):
                break

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()

    try:
        # 先补发一次当前状态（订阅之前的进度不丢）
        from ..services import tasks
        current = tasks.get(task_id)
        if current:
            await ws.send_json({k: current[k] for k in ("id", "status", "done", "total", "message")})
        while True:
            payload = await asyncio.wait_for(queue.get(), timeout=30)
            await ws.send_json(payload)
            if payload.get("status") in ("success", "failed"):
                break
    except (asyncio.TimeoutError, WebSocketDisconnect):
        pass
    finally:
        try:
            pubsub.close()
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass
