from __future__ import annotations

import logging
from pathlib import Path

from rq import get_current_job
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Certificate
from app.services import certificate_ingest, econtrole_webhook

logger = logging.getLogger(__name__)


def _log_job(message: str, *, org_id: int, path: str) -> None:
    job = get_current_job()
    job_id = job.id if job else None
    logger.info("%s org_id=%s path=%s job_id=%s", message, org_id, path, job_id)


def _log_delete_result(
    *,
    org_id: int,
    path: str,
    strategy: str,
    rowcount: int,
    found_ids_count: int,
) -> None:
    job = get_current_job()
    job_id = job.id if job else None
    logger.info(
        "job_delete_result org_id=%s path=%s job_id=%s strategy=%s rowcount=%s found_ids_count=%s",
        org_id,
        path,
        job_id,
        strategy,
        rowcount,
        found_ids_count,
    )


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
    deleted_ids: list[str] = []
    with SessionLocal() as db:
        by_path = db.execute(
            select(Certificate).where(
                Certificate.org_id == org_id, Certificate.source_path == normalized_path
            )
        ).scalars().all()
        rowcount = len(by_path)
        if rowcount > 0:
            deleted_ids.extend(str(certificate.id) for certificate in by_path)
            for certificate in by_path:
                db.delete(certificate)
            if rowcount > 1:
                job = get_current_job()
                job_id = job.id if job else None
                logger.warning(
                    "job_delete_multiple_by_path org_id=%s path=%s job_id=%s rowcount=%s",
                    org_id,
                    normalized_path,
                    job_id,
                    rowcount,
                )
            db.commit()
            _log_delete_result(
                org_id=org_id,
                path=normalized_path,
                strategy="by_path",
                rowcount=rowcount,
                found_ids_count=0,
            )
            action = "deleted"
            strategy = "by_path"
        else:
            stem = Path(normalized_path).stem
            found = db.execute(
                select(Certificate).where(Certificate.org_id == org_id, Certificate.name == stem)
            ).scalars().all()
            found_count = len(found)
            if found_count == 1:
                certificate = found[0]
                deleted_ids.append(str(certificate.id))
                db.delete(certificate)
                db.commit()
                rowcount = 1
                action = "deleted"
            elif found_count == 0:
                job = get_current_job()
                job_id = job.id if job else None
                logger.info(
                    "job_delete_not_found org_id=%s path=%s job_id=%s stem=%s",
                    org_id,
                    normalized_path,
                    job_id,
                    stem,
                )
                action = "not_found"
            else:
                job = get_current_job()
                job_id = job.id if job else None
                logger.warning(
                    "job_delete_ambiguous org_id=%s path=%s job_id=%s stem=%s count=%s ids=%s",
                    org_id,
                    normalized_path,
                    job_id,
                    stem,
                    found_count,
                    [str(certificate.id) for certificate in found],
                )
                action = "ambiguous"
            _log_delete_result(
                org_id=org_id,
                path=normalized_path,
                strategy="by_name",
                rowcount=rowcount,
                found_ids_count=found_count,
            )
            strategy = "by_name"
    if deleted_ids:
        econtrole_webhook.publish_deleted_ids(org_id=org_id, deleted_cert_ids=deleted_ids)
    _log_job("job_delete_finished", org_id=org_id, path=normalized_path)
    return {"action": action, "path": normalized_path, "strategy": strategy}
