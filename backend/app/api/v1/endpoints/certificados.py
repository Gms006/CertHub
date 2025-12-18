from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.security import require_admin_or_dev, require_view_or_higher
from app.db.session import get_db
from app.models import (
    CertInstallJob,
    Certificate,
    Device,
    JOB_STATUS_PENDING,
    JOB_STATUS_REQUESTED,
)
from app.schemas.certificate import CertificateCreate, CertificateRead
from app.schemas.install_job import InstallJobCreate, InstallJobRead

router = APIRouter(prefix="/certificados", tags=["certificados"])


@router.post("", response_model=CertificateRead, status_code=status.HTTP_201_CREATED)
async def create_certificate(
    payload: CertificateCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_dev),
) -> Certificate:
    certificate = Certificate(org_id=current_user.org_id, **payload.model_dump())
    db.add(certificate)
    log_audit(
        db=db,
        org_id=current_user.org_id,
        action="CERT_CREATED",
        entity_type="certificate",
        entity_id=certificate.id,
        actor_user_id=current_user.id,
        meta={"name": certificate.name},
    )
    db.commit()
    db.refresh(certificate)
    return certificate


@router.get("", response_model=list[CertificateRead])
async def list_certificates(
    db: Session = Depends(get_db), current_user=Depends(require_view_or_higher)
) -> list[Certificate]:
    statement = (
        select(Certificate)
        .where(Certificate.org_id == current_user.org_id)
        .order_by(Certificate.created_at)
    )
    return db.execute(statement).scalars().all()


@router.post(
    "/{certificate_id}/install",
    response_model=InstallJobRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_install_job(
    certificate_id: uuid.UUID,
    payload: InstallJobCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_view_or_higher),
) -> CertInstallJob:
    certificate = db.get(Certificate, certificate_id)
    if certificate is None or certificate.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="certificate not found")

    device = db.get(Device, payload.device_id)
    if device is None or device.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")

    if current_user.role_global in {"DEV", "ADMIN"}:
        initial_status = JOB_STATUS_PENDING
    elif current_user.auto_approve_install_jobs:
        initial_status = JOB_STATUS_PENDING
    else:
        initial_status = JOB_STATUS_REQUESTED

    job = CertInstallJob(
        org_id=current_user.org_id,
        cert_id=certificate.id,
        device_id=device.id,
        requested_by_user_id=current_user.id,
        status=initial_status,
    )
    db.add(job)
    log_audit(
        db=db,
        org_id=current_user.org_id,
        action="INSTALL_REQUESTED",
        entity_type="cert_install_job",
        entity_id=job.id,
        actor_user_id=current_user.id,
        meta={
            "cert_id": str(certificate.id),
            "device_id": str(device.id),
            "status_inicial": initial_status,
            "requested_by_user_id": str(current_user.id),
        },
    )
    db.commit()
    db.refresh(job)
    return job
