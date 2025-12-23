from __future__ import annotations

import base64
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.security import create_device_access_token, hash_token, require_device
from app.db.session import get_db
from app.models import (
    CertInstallJob,
    Certificate,
    Device,
    JOB_STATUS_DONE,
    JOB_STATUS_FAILED,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_PENDING,
)
from app.schemas.agent import (
    AgentAuthRequest,
    AgentAuthResponse,
    AgentHeartbeatRequest,
    AgentJobStatusUpdate,
    AgentPayloadResponse,
)
from app.schemas.install_job import InstallJobRead
from app.services.certificate_ingest import guess_password_from_path

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/auth", response_model=AgentAuthResponse)
def agent_auth(payload: AgentAuthRequest, db: Session = Depends(get_db)) -> AgentAuthResponse:
    device = db.get(Device, payload.device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if not device.is_allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="device blocked")
    if not device.device_token_hash:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="device token not provisioned"
        )
    token_hash = hash_token(payload.device_token)
    if not secrets.compare_digest(token_hash, device.device_token_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    access_token = create_device_access_token(device)
    return AgentAuthResponse(access_token=access_token)


@router.post("/heartbeat")
def agent_heartbeat(
    payload: AgentHeartbeatRequest,
    db: Session = Depends(get_db),
    device: Device = Depends(require_device),
) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    if payload.agent_version:
        device.agent_version = payload.agent_version
    device.last_seen_at = now
    device.last_heartbeat_at = now
    db.commit()
    return {"status": "ok"}


@router.get("/jobs", response_model=list[InstallJobRead])
def list_agent_jobs(
    db: Session = Depends(get_db),
    device: Device = Depends(require_device),
) -> list[CertInstallJob]:
    statement = (
        select(CertInstallJob)
        .where(
            CertInstallJob.org_id == device.org_id,
            CertInstallJob.device_id == device.id,
            CertInstallJob.status.in_([JOB_STATUS_PENDING, JOB_STATUS_IN_PROGRESS]),
        )
        .order_by(CertInstallJob.created_at)
    )
    return db.execute(statement).scalars().all()


@router.post("/jobs/{job_id}/claim", response_model=InstallJobRead)
def claim_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    device: Device = Depends(require_device),
) -> CertInstallJob:
    job = db.get(CertInstallJob, job_id)
    if job is None or job.org_id != device.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="job not assigned")

    now = datetime.now(timezone.utc)
    result = db.execute(
        update(CertInstallJob)
        .where(
            CertInstallJob.id == job_id,
            CertInstallJob.device_id == device.id,
            CertInstallJob.status == JOB_STATUS_PENDING,
        )
        .values(
            status=JOB_STATUS_IN_PROGRESS,
            claimed_by_device_id=device.id,
            claimed_at=now,
            started_at=now,
            updated_at=func.now(),
        )
        .returning(CertInstallJob)
    ).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job not claimable")
    log_audit(
        db=db,
        org_id=device.org_id,
        action="INSTALL_CLAIMED",
        entity_type="cert_install_job",
        entity_id=result.id,
        actor_device_id=device.id,
        meta={"job_id": str(result.id), "device_id": str(device.id)},
    )
    db.commit()
    return result


@router.get("/jobs/{job_id}/payload", response_model=AgentPayloadResponse)
def job_payload(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    device: Device = Depends(require_device),
) -> AgentPayloadResponse:
    job = db.get(CertInstallJob, job_id)
    if job is None or job.org_id != device.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="job not assigned")
    if job.status != JOB_STATUS_IN_PROGRESS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="job not in progress")

    certificate = db.get(Certificate, job.cert_id)
    if certificate is None or certificate.org_id != device.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="certificate not found")
    if not certificate.source_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="certificate source path missing")
    path = Path(certificate.source_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="certificate file not found")
    password = guess_password_from_path(path)
    if password is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="certificate password not available in filename",
        )
    raw_bytes = path.read_bytes()
    encoded = base64.b64encode(raw_bytes).decode("utf-8")
    return AgentPayloadResponse(
        job_id=job.id,
        cert_id=certificate.id,
        pfx_base64=encoded,
        password=password,
        source_path=str(path),
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/jobs/{job_id}/result", response_model=InstallJobRead)
def job_result(
    job_id: uuid.UUID,
    payload: AgentJobStatusUpdate,
    db: Session = Depends(get_db),
    device: Device = Depends(require_device),
) -> CertInstallJob:
    job = db.get(CertInstallJob, job_id)
    if job is None or job.org_id != device.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="job not assigned")

    now = datetime.now(timezone.utc)
    status_value = JOB_STATUS_DONE if payload.status == "DONE" else JOB_STATUS_FAILED
    error_code = payload.error_code if status_value == JOB_STATUS_FAILED else None
    error_message = payload.error_message if status_value == JOB_STATUS_FAILED else None
    thumbprint = payload.thumbprint if status_value == JOB_STATUS_DONE else None

    result = db.execute(
        update(CertInstallJob)
        .where(
            CertInstallJob.id == job_id,
            CertInstallJob.device_id == device.id,
            CertInstallJob.status == JOB_STATUS_IN_PROGRESS,
        )
        .values(
            status=status_value,
            finished_at=now,
            error_code=error_code,
            error_message=error_message,
            thumbprint=thumbprint,
            updated_at=func.now(),
        )
        .returning(CertInstallJob)
    ).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job not updatable")

    log_audit(
        db=db,
        org_id=device.org_id,
        action="INSTALL_DONE" if status_value == JOB_STATUS_DONE else "INSTALL_FAILED",
        entity_type="cert_install_job",
        entity_id=result.id,
        actor_device_id=device.id,
        meta={
            "job_id": str(result.id),
            "device_id": str(device.id),
            "status": status_value,
            "error_code": error_code,
        },
    )
    db.commit()
    return result
