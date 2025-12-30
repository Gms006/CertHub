from __future__ import annotations

import base64
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.rate_limit import check_rate_limit
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
    AgentCleanupEvent,
    AgentJobClaimResponse,
    AgentHeartbeatRequest,
    AgentJobStatusUpdate,
    AgentPayloadResponse,
)
from app.schemas.install_job import InstallJobRead
from app.services.certificate_ingest import guess_password_from_path

router = APIRouter(prefix="/agent", tags=["agent"])

PAYLOAD_TOKEN_TTL_SECONDS = 120
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_AUTH_PER_DEVICE = 10
RATE_LIMIT_PAYLOAD_PER_DEVICE = 5


@router.post("/auth", response_model=AgentAuthResponse)
def agent_auth(payload: AgentAuthRequest, db: Session = Depends(get_db)) -> AgentAuthResponse:
    allowed, _ = check_rate_limit(
        f"rl:agent_auth:{payload.device_id}",
        RATE_LIMIT_AUTH_PER_DEVICE,
        RATE_LIMIT_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit")
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


@router.post("/cleanup")
def agent_cleanup_event(
    payload: AgentCleanupEvent,
    db: Session = Depends(get_db),
    device: Device = Depends(require_device),
) -> dict[str, str]:
    log_audit(
        db=db,
        org_id=device.org_id,
        action="CERT_REMOVED_18H",
        entity_type="cert_cleanup",
        actor_device_id=device.id,
        meta={
            "device_id": str(device.id),
            "removed_count": payload.removed_count,
            "failed_count": payload.failed_count,
            "removed_thumbprints": payload.removed_thumbprints,
            "failed_thumbprints": payload.failed_thumbprints,
            "mode": payload.mode,
            "ran_at_local": payload.ran_at_local,
        },
    )
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


@router.post("/jobs/{job_id}/claim", response_model=AgentJobClaimResponse)
def claim_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    device: Device = Depends(require_device),
) -> AgentJobClaimResponse:
    job = db.get(CertInstallJob, job_id)
    if job is None or job.org_id != device.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.device_id != device.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="job not assigned")

    now = datetime.now(timezone.utc)
    payload_token = secrets.token_urlsafe(32)
    payload_token_hash = hash_token(payload_token)
    expires_at = now + timedelta(seconds=PAYLOAD_TOKEN_TTL_SECONDS)
    if job.status == JOB_STATUS_IN_PROGRESS and job.claimed_by_device_id == device.id:
        job.payload_token_hash = payload_token_hash
        job.payload_token_expires_at = expires_at
        job.payload_token_used_at = None
        job.payload_token_device_id = device.id
        job.updated_at = now
        db.commit()
        job_data = InstallJobRead.model_validate(job, from_attributes=True).model_dump()
        return AgentJobClaimResponse(**job_data, payload_token=payload_token)
    if job.status == JOB_STATUS_IN_PROGRESS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job not claimable")
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
            payload_token_hash=payload_token_hash,
            payload_token_expires_at=expires_at,
            payload_token_used_at=None,
            payload_token_device_id=device.id,
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
    job_data = InstallJobRead.model_validate(result, from_attributes=True).model_dump()
    return AgentJobClaimResponse(**job_data, payload_token=payload_token)


@router.get("/jobs/{job_id}/payload", response_model=AgentPayloadResponse)
def job_payload(
    job_id: uuid.UUID,
    request: Request,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
    device: Device = Depends(require_device),
) -> AgentPayloadResponse:
    allowed, _ = check_rate_limit(
        f"rl:agent_payload:{device.id}",
        RATE_LIMIT_PAYLOAD_PER_DEVICE,
        RATE_LIMIT_WINDOW_SECONDS,
    )
    if not allowed:
        log_audit(
            db=db,
            org_id=device.org_id,
            action="PAYLOAD_RATE_LIMITED",
            entity_type="cert_install_job",
            actor_device_id=device.id,
            meta={"device_id": str(device.id), "ip": request.client.host if request.client else None},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit")

    job = db.get(CertInstallJob, job_id)
    if job is None or job.org_id != device.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.device_id != device.id:
        log_audit(
            db=db,
            org_id=device.org_id,
            action="PAYLOAD_DENIED",
            entity_type="cert_install_job",
            entity_id=job_id,
            actor_device_id=device.id,
            meta={
                "reason": "device_mismatch",
                "job_id": str(job_id),
                "ip": request.client.host if request.client else None,
            },
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="job not assigned")
    if job.status != JOB_STATUS_IN_PROGRESS:
        log_audit(
            db=db,
            org_id=device.org_id,
            action="PAYLOAD_DENIED",
            entity_type="cert_install_job",
            entity_id=job_id,
            actor_device_id=device.id,
            meta={
                "reason": "job_not_in_progress",
                "job_status": job.status,
                "job_id": str(job_id),
                "ip": request.client.host if request.client else None,
            },
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="job not in progress")
    if job.claimed_by_device_id != device.id:
        log_audit(
            db=db,
            org_id=device.org_id,
            action="PAYLOAD_DENIED",
            entity_type="cert_install_job",
            entity_id=job_id,
            actor_device_id=device.id,
            meta={
                "reason": "device_mismatch",
                "job_id": str(job_id),
                "ip": request.client.host if request.client else None,
            },
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="job not claimed by device")

    if not token:
        log_audit(
            db=db,
            org_id=device.org_id,
            action="PAYLOAD_DENIED",
            entity_type="cert_install_job",
            entity_id=job_id,
            actor_device_id=device.id,
            meta={
                "reason": "missing_token",
                "job_id": str(job_id),
                "ip": request.client.host if request.client else None,
            },
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="missing token")

    locked_job = db.execute(
        select(CertInstallJob)
        .where(CertInstallJob.id == job_id, CertInstallJob.org_id == device.org_id)
        .with_for_update()
    ).scalar_one_or_none()
    if locked_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if locked_job.payload_token_used_at is not None:
        log_audit(
            db=db,
            org_id=device.org_id,
            action="PAYLOAD_DENIED",
            entity_type="cert_install_job",
            entity_id=job_id,
            actor_device_id=device.id,
            meta={
                "reason": "token_used",
                "job_id": str(job_id),
                "ip": request.client.host if request.client else None,
            },
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="token already used")
    if locked_job.payload_token_device_id != device.id:
        log_audit(
            db=db,
            org_id=device.org_id,
            action="PAYLOAD_DENIED",
            entity_type="cert_install_job",
            entity_id=job_id,
            actor_device_id=device.id,
            meta={
                "reason": "device_mismatch",
                "job_id": str(job_id),
                "ip": request.client.host if request.client else None,
            },
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="token device mismatch")
    if locked_job.payload_token_expires_at is None or locked_job.payload_token_hash is None:
        log_audit(
            db=db,
            org_id=device.org_id,
            action="PAYLOAD_DENIED",
            entity_type="cert_install_job",
            entity_id=job_id,
            actor_device_id=device.id,
            meta={
                "reason": "missing_token",
                "job_id": str(job_id),
                "ip": request.client.host if request.client else None,
            },
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="missing token")
    expires_at = locked_job.payload_token_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is None or datetime.now(timezone.utc) > expires_at:
        log_audit(
            db=db,
            org_id=device.org_id,
            action="PAYLOAD_DENIED",
            entity_type="cert_install_job",
            entity_id=job_id,
            actor_device_id=device.id,
            meta={
                "reason": "token_expired",
                "job_id": str(job_id),
                "ip": request.client.host if request.client else None,
            },
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="token expired")
    if not secrets.compare_digest(hash_token(token), locked_job.payload_token_hash):
        log_audit(
            db=db,
            org_id=device.org_id,
            action="PAYLOAD_DENIED",
            entity_type="cert_install_job",
            entity_id=job_id,
            actor_device_id=device.id,
            meta={
                "reason": "token_mismatch",
                "job_id": str(job_id),
                "ip": request.client.host if request.client else None,
            },
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="token mismatch")

    locked_job.payload_token_used_at = datetime.now(timezone.utc)
    db.commit()

    certificate = db.get(Certificate, locked_job.cert_id)
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
    log_audit(
        db=db,
        org_id=device.org_id,
        action="PAYLOAD_ISSUED",
        entity_type="cert_install_job",
        entity_id=locked_job.id,
        actor_device_id=device.id,
        meta={
            "job_id": str(locked_job.id),
            "device_id": str(device.id),
            "ip": request.client.host if request.client else None,
        },
    )
    db.commit()
    return AgentPayloadResponse(
        job_id=locked_job.id,
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
        db.refresh(job)
        action = "RESULT_DUPLICATE" if job.status in {JOB_STATUS_DONE, JOB_STATUS_FAILED} else "RESULT_DENIED"
        log_audit(
            db=db,
            org_id=device.org_id,
            action=action,
            entity_type="cert_install_job",
            entity_id=job_id,
            actor_device_id=device.id,
            meta={
                "job_id": str(job_id),
                "device_id": str(device.id),
                "status": job.status,
            },
        )
        db.commit()
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
