# -*- coding: utf-8 -*-
"""
Redis 接入层：连接管理、JSON 缓存、计数限流、发布订阅。

优先连接真实 Redis（REDIS_URL），连不上自动降级到进程内 fakeredis，
保证系统在 Redis 服务停止时依然可用（cache_backend 标识当前后端）。
"""
import json
from urllib.parse import urlparse

import redis as redis_lib

from ..config import REDIS_URL

_client = None
_backend = ""


def get_client():
    """单例 Redis 客户端；真实 Redis 不可用时降级 fakeredis"""
    global _client, _backend
    if _client is not None:
        return _client
    try:
        c = redis_lib.Redis.from_url(
            REDIS_URL, socket_connect_timeout=1, socket_timeout=2,
            decode_responses=True, protocol=2,  # Windows 版 Redis 3.0 不支持 RESP3(HELLO)
        )
        c.ping()
        _client, _backend = c, "redis"
    except Exception:
        import fakeredis
        _client, _backend = fakeredis.FakeStrictRedis(decode_responses=True), "fakeredis"
    return _client


def backend_name() -> str:
    get_client()
    return _backend


PREFIX = "chatkb:"


def get_json(key: str):
    raw = get_client().get(PREFIX + key)
    return json.loads(raw) if raw else None


def set_json(key: str, value, ttl: int | None = None):
    get_client().set(PREFIX + key, json.dumps(value, ensure_ascii=False), ex=ttl)


def delete_pattern(pattern: str) -> int:
    """按前缀批量删除（SCAN 避免阻塞）"""
    n = 0
    for k in get_client().scan_iter(PREFIX + pattern, count=500):
        get_client().delete(k)
        n += 1
    return n


def incr_with_ttl(key: str, ttl_seconds: int) -> int:
    """计数器 + 首次设置过期（INCR + EXPIRE），用于滑动限流"""
    c = get_client()
    full = PREFIX + key
    val = c.incr(full)
    if val == 1:
        c.expire(full, ttl_seconds)
    return int(val)


def publish(channel: str, payload: dict):
    try:
        get_client().publish(PREFIX + channel, json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


def subscribe(channel: str):
    """返回 pubsub 对象，调用方自行 listen()"""
    ps = get_client().pubsub(ignore_subscribe_messages=True)
    ps.subscribe(PREFIX + channel)
    return ps
