from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

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
    UserDevice,
)
from app.schemas.certificate import CertificateCreate, CertificateRead
from app.schemas.install_job import InstallJobCreate, InstallJobRead

router = APIRouter(prefix="/certificados", tags=["certificados"])

def sanitize_certificate_name(value: str) -> str:
    sanitized = value
    patterns = [
        r"senha\s*[:=]?\s*[^\s]+",
        r"senha[_-]?[^\s]+",
        r"\bsenha\b",
    ]
    for pattern in patterns:
        sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"[_-]{2,}", "-", sanitized)
    sanitized = re.sub(r"\s{2,}", " ", sanitized)
    sanitized = re.sub(r"[-_ ]+$", "", sanitized)
    sanitized = re.sub(r"^[-_ ]+", "", sanitized)
    return sanitized.strip()


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
    certificates = db.execute(statement).scalars().all()
    payload: list[CertificateRead] = []
    for cert in certificates:
        response = CertificateRead.model_validate(cert, from_attributes=True)
        payload.append(
            response.model_copy(update={"name": sanitize_certificate_name(response.name)})
        )
    return payload


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

    # Bloqueio global do device (toggle ADMIN: device.is_allowed)
    if not device.is_allowed:
        log_audit(
            db=db,
            org_id=current_user.org_id,
            action="INSTALL_DENIED",
            entity_type="device",
            entity_id=device.id,
            actor_user_id=current_user.id,
            meta={
                "reason": "device_not_allowed",
                "cert_id": str(certificate.id),
                "device_id": str(device.id),
                "requested_by_user_id": str(current_user.id),
            },
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="device not allowed")

    if current_user.role_global == "VIEW":
        allowed_device = db.execute(
            select(UserDevice)
            .where(
                UserDevice.device_id == device.id,
                UserDevice.user_id == current_user.id,
                UserDevice.is_allowed.is_(True),
            )
            .limit(1)
        ).scalar_one_or_none()
        if device.assigned_user_id != current_user.id and allowed_device is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="device not allowed")

    auto_approved = False
    auto_reason = None
    if current_user.role_global in {"DEV", "ADMIN"}:
        initial_status = JOB_STATUS_PENDING
        auto_approved = True
        auto_reason = "role"
    elif current_user.auto_approve_install_jobs is True:
        initial_status = JOB_STATUS_PENDING
        auto_approved = True
        auto_reason = "flag"
    elif device.auto_approve is True:
        initial_status = JOB_STATUS_PENDING
        auto_approved = True
        auto_reason = "device"
    else:
        initial_status = JOB_STATUS_REQUESTED

    job = CertInstallJob(
        org_id=current_user.org_id,
        cert_id=certificate.id,
        device_id=device.id,
        requested_by_user_id=current_user.id,
        status=initial_status,
    )
    if auto_approved:
        job.approved_by_user_id = current_user.id
        job.approved_at = datetime.now(timezone.utc)
    db.add(job)
    db.flush()
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
    if auto_approved:
        log_audit(
            db=db,
            org_id=current_user.org_id,
            action="INSTALL_APPROVED",
            entity_type="cert_install_job",
            entity_id=job.id,
            actor_user_id=current_user.id,
            meta={"auto": True, "via": auto_reason, "job_id": str(job.id)},
        )
    db.commit()
    db.refresh(job)
    return job
