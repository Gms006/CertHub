from __future__ import annotations

import os
from functools import lru_cache
from typing import Tuple

import redis

DEFAULT_REDIS_URL = "redis://localhost:6379/0"


@lru_cache(maxsize=1)
def _get_redis() -> redis.Redis:
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    return redis.Redis.from_url(redis_url)


def check_rate_limit(key: str, limit: int, window_seconds: int) -> Tuple[bool, int]:
    client = _get_redis()
    try:
        with client.pipeline() as pipe:
            pipe.incr(key)
            pipe.ttl(key)
            count, ttl = pipe.execute()
        if ttl == -1:
            client.expire(key, window_seconds)
        return count <= limit, int(count)
    except redis.RedisError:
        return True, 0
