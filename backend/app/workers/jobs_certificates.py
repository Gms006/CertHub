from __future__ import annotations

import logging
from pathlib import Path

from rq import get_current_job
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Certificate
from app.services import certificate_ingest

logger = logging.getLogger(__name__)


def _log_job(message: str, *, org_id: int, path: str) -> None:
    job = get_current_job()
    job_id = job.id if job else None
    logger.info("%s org_id=%s path=%s job_id=%s", message, org_id, path, job_id)


def ingest_pfx_file(org_id: int, path: str) -> dict[str, str | None]:
    normalized_path = str(Path(path).expanduser().resolve(strict=False))
    _log_job("job_ingest_started", org_id=org_id, path=normalized_path)
    with SessionLocal() as db:
        result = certificate_ingest.ingest_certificate_from_path(
            db, org_id=org_id, path=Path(normalized_path)
        )
    _log_job("job_ingest_finished", org_id=org_id, path=normalized_path)
    return result


def delete_certificate_by_path(org_id: int, path: str) -> dict[str, str | None]:
    normalized_path = str(Path(path).expanduser().resolve(strict=False))
    _log_job("job_delete_started", org_id=org_id, path=normalized_path)
    with SessionLocal() as db:
        certificate = db.execute(
            select(Certificate).where(
                Certificate.org_id == org_id, Certificate.source_path == normalized_path
            )
        ).scalar_one_or_none()
        if certificate:
            db.delete(certificate)
            db.commit()
            action = "deleted"
        else:
            action = "not_found"
    _log_job("job_delete_finished", org_id=org_id, path=normalized_path)
    return {"action": action, "path": normalized_path}
