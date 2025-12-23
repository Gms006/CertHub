from __future__ import annotations

import logging
import os

from rq import SimpleWorker
from rq.timeouts import TimerDeathPenalty

from app.workers.queue import get_queue, get_redis

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    redis_conn = get_redis()
    queue = get_queue(redis_conn)
    logger.info("rq_worker_started queue=%s", queue.name)
    worker = SimpleWorker([queue], connection=redis_conn)
    worker.death_penalty_class = TimerDeathPenalty
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
