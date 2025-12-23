from __future__ import annotations

import hashlib
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileSystemEvent, FileMovedEvent
from watchdog.observers import Observer

from app.core.config import settings
from app.workers.jobs_certificates import delete_certificate_by_path, ingest_pfx_file
from app.workers.queue import enqueue_unique, get_queue, get_redis, normalize_path

logger = logging.getLogger(__name__)

PFX_EXTENSION = ".pfx"


@dataclass
class WatcherConfig:
    org_id: int
    root_path: Path
    debounce_seconds: float
    max_events_per_minute: int


class PfxDirectoryHandler(FileSystemEventHandler):
    def __init__(self, config: WatcherConfig):
        self.config = config
        self.queue = get_queue(get_redis())
        self._last_event_at: dict[str, float] = {}
        self._event_times: deque[float] = deque()

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle_file_event("created", event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle_file_event("modified", event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._handle_file_event("deleted", event)

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            return
        src_path = normalize_path(event.src_path)
        dest_path = normalize_path(event.dest_path)
        src_in_root = self._is_in_root(src_path)
        dest_in_root = self._is_in_root(dest_path)
        src_is_pfx = src_path.lower().endswith(PFX_EXTENSION)
        dest_is_pfx = dest_path.lower().endswith(PFX_EXTENSION)

        if src_in_root and src_is_pfx and (not dest_in_root or not dest_is_pfx):
            self._enqueue_delete(src_path, "moved")
        elif dest_in_root and dest_is_pfx and (not src_in_root or not src_is_pfx):
            self._enqueue_ingest(dest_path, "moved")
        elif src_in_root and dest_in_root and src_is_pfx and dest_is_pfx:
            self._enqueue_delete(src_path, "moved")
            self._enqueue_ingest(dest_path, "moved")

    def _handle_file_event(self, event_name: str, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        raw_path = normalize_path(event.src_path)
        if not self._is_in_root(raw_path):
            return
        if not raw_path.lower().endswith(PFX_EXTENSION):
            return
        if event_name == "deleted":
            self._enqueue_delete(raw_path, event_name)
        else:
            self._enqueue_ingest(raw_path, event_name)

    def _is_in_root(self, raw_path: str) -> bool:
        path = Path(raw_path)
        return path.parent == self.config.root_path

    def _rate_limited(self) -> bool:
        if self.config.max_events_per_minute <= 0:
            return False
        now = time.monotonic()
        window_start = now - 60.0
        while self._event_times and self._event_times[0] < window_start:
            self._event_times.popleft()
        if len(self._event_times) >= self.config.max_events_per_minute:
            return True
        self._event_times.append(now)
        return False

    def _debounced(self, path: str) -> bool:
        if self.config.debounce_seconds <= 0:
            return False
        now = time.monotonic()
        last = self._last_event_at.get(path)
        if last is not None and (now - last) < self.config.debounce_seconds:
            return True
        self._last_event_at[path] = now
        return False

    def _enqueue_ingest(self, path: str, event_name: str) -> None:
        if self._rate_limited():
            logger.warning("watcher_rate_limited event=%s path=%s", event_name, path)
            return
        if self._debounced(path):
            logger.info("watcher_debounced event=%s path=%s", event_name, path)
            return
        job_id = self._build_job_id("ing", path)
        _, deduped = enqueue_unique(
            self.queue,
            ingest_pfx_file,
            self.config.org_id,
            path,
            job_id=job_id,
        )
        logger.info(
            "watcher_enqueue event=%s action=ingest path=%s job_id=%s result=%s",
            event_name,
            path,
            job_id,
            "existing" if deduped else "new",
        )

    def _enqueue_delete(self, path: str, event_name: str) -> None:
        if self._rate_limited():
            logger.warning("watcher_rate_limited event=%s path=%s", event_name, path)
            return
        if self._debounced(path):
            logger.info("watcher_debounced event=%s path=%s", event_name, path)
            return
        job_id = self._build_job_id("del", path)
        _, deduped = enqueue_unique(
            self.queue,
            delete_certificate_by_path,
            self.config.org_id,
            path,
            job_id=job_id,
        )
        logger.info(
            "watcher_enqueue event=%s action=delete path=%s job_id=%s result=%s",
            event_name,
            path,
            job_id,
            "existing" if deduped else "new",
        )

    def _build_job_id(self, action: str, path: str) -> str:
        path_key = normalize_path(path).lower()
        digest = hashlib.sha1(path_key.encode("utf-8")).hexdigest()
        action_prefix = "cert_ing" if action == "ing" else "cert_del"
        return f"{action_prefix}__{self.config.org_id}__{digest}"


def _load_config() -> WatcherConfig:
    org_id = int(os.getenv("ORG_ID", str(settings.default_org_id)))
    root_path = Path(os.getenv("CERTIFICADOS_ROOT", str(settings.certs_root_path)))
    root_path = root_path.expanduser().resolve(strict=False)
    debounce_seconds = float(os.getenv("WATCHER_DEBOUNCE_SECONDS", "2"))
    max_events = int(os.getenv("WATCHER_MAX_EVENTS_PER_MINUTE", "60"))
    return WatcherConfig(
        org_id=org_id,
        root_path=root_path,
        debounce_seconds=debounce_seconds,
        max_events_per_minute=max_events,
    )


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = _load_config()
    if not config.root_path.exists() or not config.root_path.is_dir():
        raise FileNotFoundError(f"CERTIFICADOS_ROOT not found: {config.root_path}")
    logger.info(
        "watcher_started org_id=%s root=%s debounce=%s rate_limit=%s",
        config.org_id,
        config.root_path,
        config.debounce_seconds,
        config.max_events_per_minute,
    )
    event_handler = PfxDirectoryHandler(config)
    observer = Observer()
    observer.schedule(event_handler, str(config.root_path), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("watcher_shutdown")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
