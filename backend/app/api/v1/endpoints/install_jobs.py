from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.security import require_admin_or_dev, require_view_or_higher
from app.db.session import get_db
from app.models import (
    CertInstallJob,
    JOB_STATUS_CANCELED,
    JOB_STATUS_PENDING,
    JOB_STATUS_REQUESTED,
)
from app.schemas.install_job import InstallJobApproveRequest, InstallJobRead

router = APIRouter(prefix="/install-jobs", tags=["install-jobs"])


@router.get("", response_model=list[InstallJobRead])
async def list_install_jobs(
    mine: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_dev),
) -> list[CertInstallJob]:
    if not mine:
        statement = select(CertInstallJob).where(CertInstallJob.org_id == current_user.org_id)
    else:
        statement = select(CertInstallJob).where(
            CertInstallJob.org_id == current_user.org_id,
            CertInstallJob.requested_by_user_id == current_user.id,
        )
    statement = statement.order_by(CertInstallJob.created_at.desc())
    return db.execute(statement).scalars().all()


@router.get("/mine", response_model=list[InstallJobRead])
async def list_my_jobs(
    db: Session = Depends(get_db), current_user=Depends(require_view_or_higher)
) -> list[CertInstallJob]:
    statement = select(CertInstallJob).where(
        CertInstallJob.org_id == current_user.org_id,
        CertInstallJob.requested_by_user_id == current_user.id,
    )
    statement = statement.order_by(CertInstallJob.created_at.desc())
    return db.execute(statement).scalars().all()


@router.post("/{job_id}/approve", response_model=InstallJobRead)
async def approve_job(
    job_id: uuid.UUID,
    payload: InstallJobApproveRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_dev),
) -> CertInstallJob:
    job = db.get(CertInstallJob, job_id)
    if job is None or job.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.status != JOB_STATUS_REQUESTED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid status")

    job.status = JOB_STATUS_PENDING
    job.approved_by_user_id = current_user.id
    job.approved_at = datetime.now(timezone.utc)
    log_audit(
        db=db,
        org_id=current_user.org_id,
        action="INSTALL_APPROVED",
        entity_type="cert_install_job",
        entity_id=job.id,
        actor_user_id=current_user.id,
        meta={"job_id": str(job.id), "reason": payload.reason if payload else None},
    )
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/deny", response_model=InstallJobRead)
async def deny_job(
    job_id: uuid.UUID,
    payload: InstallJobApproveRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_dev),
) -> CertInstallJob:
    job = db.get(CertInstallJob, job_id)
    if job is None or job.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.status != JOB_STATUS_REQUESTED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid status")

    job.status = JOB_STATUS_CANCELED
    job.approved_by_user_id = current_user.id
    job.approved_at = datetime.now(timezone.utc)
    log_audit(
        db=db,
        org_id=current_user.org_id,
        action="INSTALL_DENIED",
        entity_type="cert_install_job",
        entity_id=job.id,
        actor_user_id=current_user.id,
        meta={"job_id": str(job.id), "reason": payload.reason if payload else None},
    )
    db.commit()
    db.refresh(job)
    return job
