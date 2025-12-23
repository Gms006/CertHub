from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import redis
from rq import Queue
from rq.job import JobStatus

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_QUEUE_NAME = "certs"

logger = logging.getLogger(__name__)

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


def enqueue_unique(queue: Queue, func, *args, job_id: str, **kwargs) -> tuple[object, bool]:
    existing_job = queue.fetch_job(job_id)
    if existing_job is not None:
        status = existing_job.get_status()
        if status in {JobStatus.QUEUED, JobStatus.STARTED, JobStatus.DEFERRED}:
            logger.info("queue_deduped job_id=%s status=%s", job_id, status)
            return existing_job, True
        try:
            existing_job.cancel()
            existing_job.delete(remove_from_queue=True)
            logger.info("queue_reenqueue job_id=%s status=%s", job_id, status)
        except Exception:
            logger.warning("queue_reenqueue_failed job_id=%s status=%s", job_id, status)
        new_job = queue.enqueue(func, *args, job_id=job_id, **kwargs)
        return new_job, False
    new_job = queue.enqueue(func, *args, job_id=job_id, **kwargs)
    logger.info("queue_enqueued job_id=%s", job_id)
    return new_job, False
