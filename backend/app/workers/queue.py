from __future__ import annotations

import hashlib
import os
from pathlib import Path

import redis
from rq import Queue

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_QUEUE_NAME = "certs"


def normalize_path(raw_path: str | Path) -> str:
    path = Path(raw_path).expanduser().resolve(strict=False)
    return str(path)


def sanitize_job_id(raw_path: str | Path) -> str:
    normalized = normalize_path(raw_path).lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def get_redis() -> redis.Redis:
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    return redis.Redis.from_url(redis_url)


def get_queue(connection: redis.Redis | None = None) -> Queue:
    if connection is None:
        connection = get_redis()
    queue_name = os.getenv("RQ_QUEUE_NAME", DEFAULT_QUEUE_NAME)
    return Queue(queue_name, connection=connection)


def enqueue_unique(queue: Queue, func, *args, job_id: str, **kwargs):
    existing_job = queue.fetch_job(job_id)
    if existing_job is not None:
        return existing_job
    return queue.enqueue(func, *args, job_id=job_id, **kwargs)
