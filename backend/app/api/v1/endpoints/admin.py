from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.audit import log_audit
from app.core.config import settings
from app.core.security import require_admin_or_dev, require_dev, require_view_or_higher
from app.db.session import get_db
from app.core.security import AUTH_TOKEN_PURPOSE_SET_PASSWORD, generate_token, hash_token
from app.models import (
    AuthToken,
    CertInstallJob,
    Device,
    JOB_STATUS_FAILED,
    JOB_STATUS_IN_PROGRESS,
    User,
    UserDevice,
)
from app.schemas.cert_ingest import CertIngestRequest, CertIngestResponse
from app.schemas.device import (
    DeviceCreate,
    DeviceCreateResponse,
    DeviceRead,
    DeviceTokenRotateResponse,
    DeviceUpdate,
)
from app.schemas.user import UserCreate, UserCreateResponse, UserRead, UserUpdate
from app.schemas.user_device import UserDeviceCreate, UserDeviceRead, UserDeviceReadWithUser
from app.services.certificate_ingest import ingest_certificates_from_fs

router = APIRouter(prefix="/admin", tags=["admin"])


# User management


def resolve_assigned_user(
    db: Session, org_id: int, assigned_user_id: uuid.UUID | None
) -> User | None:
    if assigned_user_id is None:
        return None
    user = db.get(User, assigned_user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="assigned user not found"
        )
    if user.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="assigned user not in org"
        )
    return user


@router.post("/users", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_dev),
) -> UserCreateResponse:
    org_id = current_user.org_id
    user = User(org_id=org_id, **user_in.model_dump())
    db.add(user)
    db.flush()
    setup_token = generate_token()
    setup_expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.set_password_token_ttl_min
    )
    auth_token = AuthToken(
        user_id=user.id,
        token_hash=hash_token(setup_token),
        purpose=AUTH_TOKEN_PURPOSE_SET_PASSWORD,
        expires_at=setup_expires_at,
    )
    db.add(auth_token)
    log_audit(
        db=db,
        org_id=org_id,
        action="USER_CREATED",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=current_user.id,
        meta={"ad_username": user.ad_username},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.orig))
    db.refresh(user)
    response = UserCreateResponse.model_validate(user, from_attributes=True)
    return response.model_copy(update={"setup_token": setup_token})


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db), current_user=Depends(require_dev)
) -> list[User]:
    statement = (
        select(User)
        .where(User.org_id == current_user.org_id)
        .order_by(User.created_at)
    )
    return db.execute(statement).scalars().all()


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_dev),
) -> User:
    user = db.get(User, user_id)
    if user is None or user.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    changes: dict[str, list] = {}

    def apply_change(field: str, value) -> None:
        if value is None:
            return
        old_value = getattr(user, field)
        if old_value != value:
            setattr(user, field, value)
            changes[field] = [old_value, value]

    if user_in.role_global is not None or user_in.is_active is not None:
        if current_user.role_global != "DEV":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    apply_change("auto_approve_install_jobs", user_in.auto_approve_install_jobs)
    apply_change("role_global", user_in.role_global)
    apply_change("is_active", user_in.is_active)
    apply_change("ad_username", user_in.ad_username)
    apply_change("email", user_in.email)
    apply_change("nome", user_in.nome)

    if not changes:
        return user

    log_audit(
        db=db,
        org_id=current_user.org_id,
        action="USER_UPDATED",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=current_user.id,
        meta={"changes": changes},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.orig))
    db.refresh(user)
    return user


@router.post("/devices", response_model=DeviceCreateResponse, status_code=status.HTTP_201_CREATED)
def create_device(
    device_in: DeviceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_dev),
) -> DeviceCreateResponse:
    org_id = current_user.org_id
    payload = device_in.model_dump()
    assigned_user_id = payload.pop("assigned_user_id", None)
    assigned_user = resolve_assigned_user(db, org_id, assigned_user_id)
    device_token = generate_token()
    token_created_at = datetime.now(timezone.utc)
    try:
        device = Device(org_id=org_id, **payload)
        device.assigned_user = assigned_user
        device.device_token_hash = hash_token(device_token)
        device.token_created_at = token_created_at
        db.add(device)
        db.flush()
        db.refresh(device)
        log_audit(
            db=db,
            org_id=org_id,
            action="DEVICE_CREATED",
            entity_type="device",
            entity_id=device.id,
            actor_user_id=current_user.id,
            meta={"hostname": device.hostname},
        )
        response = DeviceCreateResponse(
            id=device.id,
            org_id=device.org_id,
            hostname=device.hostname,
            domain=device.domain,
            os_version=device.os_version,
            agent_version=device.agent_version,
            last_seen_at=device.last_seen_at,
            last_heartbeat_at=device.last_heartbeat_at,
            is_allowed=device.is_allowed,
            assigned_user_id=device.assigned_user_id,
            created_at=device.created_at,
            assigned_user=UserRead.model_validate(assigned_user, from_attributes=True)
            if assigned_user
            else None,
            device_token=device_token,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.orig))
    except Exception:
        db.rollback()
        raise
    return response


@router.post("/devices/{device_id}/rotate-token", response_model=DeviceTokenRotateResponse)
def rotate_device_token(
    device_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_dev),
) -> DeviceTokenRotateResponse:
    device = db.get(Device, device_id)
    if device is None or device.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")
    device_token = generate_token()
    token_created_at = datetime.now(timezone.utc)
    try:
        device.device_token_hash = hash_token(device_token)
        device.token_created_at = token_created_at
        db.add(device)
        db.flush()
        log_audit(
            db=db,
            org_id=current_user.org_id,
            action="DEVICE_TOKEN_ROTATED",
            entity_type="device",
            entity_id=device.id,
            actor_user_id=current_user.id,
            meta={"device_id": str(device.id)},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.orig))
    except Exception:
        db.rollback()
        raise
    return DeviceTokenRotateResponse(
        device_id=device.id,
        device_token=device_token,
        token_created_at=token_created_at,
    )


@router.get("/devices", response_model=list[DeviceRead])
def list_devices(
    db: Session = Depends(get_db), current_user=Depends(require_view_or_higher)
) -> list[Device]:
    last_job_subquery = (
        select(
            CertInstallJob.device_id.label("device_id"),
            func.max(CertInstallJob.created_at).label("last_job_created_at"),
        )
        .where(CertInstallJob.org_id == current_user.org_id)
        .group_by(CertInstallJob.device_id)
        .subquery()
    )
    statement = (
        select(Device, last_job_subquery.c.last_job_created_at)
        .outerjoin(last_job_subquery, last_job_subquery.c.device_id == Device.id)
        .where(Device.org_id == current_user.org_id)
        .options(selectinload(Device.assigned_user))
        .order_by(Device.created_at)
    )
    results = db.execute(statement).all()
    payload: list[DeviceRead] = []
    for device, last_job_created_at in results:
        response = DeviceRead.model_validate(device, from_attributes=True)
        response = response.model_copy(update={"last_seen_at": last_job_created_at})
        payload.append(response)
    return payload


@router.post("/jobs/reap")
def reap_stale_jobs(
    threshold_minutes: int = Query(default=60, ge=1, le=10080),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_dev),
) -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
    statement = (
        select(CertInstallJob)
        .where(
            CertInstallJob.org_id == current_user.org_id,
            CertInstallJob.status == JOB_STATUS_IN_PROGRESS,
            CertInstallJob.started_at.is_not(None),
            CertInstallJob.started_at <= cutoff,
        )
        .order_by(CertInstallJob.started_at)
    )
    stale_jobs = db.execute(statement).scalars().all()
    if not stale_jobs:
        return {"reaped": 0}

    now = datetime.now(timezone.utc)
    for job in stale_jobs:
        job.status = JOB_STATUS_FAILED
        job.finished_at = now
        job.error_code = "TIMEOUT"
        job.error_message = f"Job timed out after {threshold_minutes} minutes"
        job.updated_at = now
        log_audit(
            db=db,
            org_id=current_user.org_id,
            action="JOB_REAPED",
            entity_type="cert_install_job",
            entity_id=job.id,
            actor_user_id=current_user.id,
            meta={
                "job_id": str(job.id),
                "status": job.status,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "threshold_minutes": threshold_minutes,
            },
        )
    db.commit()
    return {"reaped": len(stale_jobs)}


@router.patch("/devices/{device_id}", response_model=DeviceRead)
def update_device(
    device_id: uuid.UUID,
    payload: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_dev),
) -> Device:
    device = db.get(Device, device_id)
    if device is None or device.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")

    changes: dict[str, list] = {}

    def apply_change(field: str, value) -> None:
        if value is None:
            return
        old_value = getattr(device, field)
        if old_value != value:
            setattr(device, field, value)
            changes[field] = [old_value, value]

    apply_change("is_allowed", payload.is_allowed)
    if "assigned_user_id" in payload.model_fields_set:
        assigned_user_id = payload.assigned_user_id
        assigned_user = resolve_assigned_user(db, current_user.org_id, assigned_user_id)
        old_value = device.assigned_user_id
        if old_value != assigned_user_id:
            device.assigned_user_id = assigned_user_id
            device.assigned_user = assigned_user
            changes["assigned_user_id"] = [old_value, assigned_user_id]

    if changes:
        log_audit(
            db=db,
            org_id=current_user.org_id,
            action="DEVICE_UPDATED",
            entity_type="device",
            entity_id=device.id,
            actor_user_id=current_user.id,
            meta={"changes": changes},
        )
        db.commit()
        db.refresh(device)
    return device


@router.post(
    "/user-devices",
    response_model=UserDeviceRead,
    status_code=status.HTTP_201_CREATED,
)
def link_user_device(
    payload: UserDeviceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_dev),
) -> UserDevice:
    link = UserDevice(**payload.model_dump())
    db.add(link)
    log_audit(
        db=db,
        org_id=current_user.org_id,
        action="USER_DEVICE_LINKED",
        entity_type="user_device",
        entity_id=f"{link.user_id}:{link.device_id}",
        actor_user_id=current_user.id,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.orig))
    db.refresh(link)
    return link


@router.get("/user-devices", response_model=list[UserDeviceReadWithUser])
def list_user_devices(
    db: Session = Depends(get_db), current_user=Depends(require_admin_or_dev)
) -> list[UserDeviceReadWithUser]:
    statement = (
        select(UserDevice, User)
        .join(User, UserDevice.user_id == User.id)
        .join(Device, UserDevice.device_id == Device.id)
        .where(Device.org_id == current_user.org_id)
        .order_by(UserDevice.created_at.desc())
    )
    results = db.execute(statement).all()
    payload: list[UserDeviceReadWithUser] = []
    for link, user in results:
        payload.append(
            UserDeviceReadWithUser(
                user_id=link.user_id,
                device_id=link.device_id,
                is_allowed=link.is_allowed,
                created_at=link.created_at,
                user=UserRead.model_validate(user, from_attributes=True),
            )
        )
    return payload


@router.post(
    "/certificates/ingest-from-fs",
    response_model=CertIngestResponse,
    status_code=status.HTTP_200_OK,
)
def ingest_certificates_from_filesystem(
    payload: CertIngestRequest = CertIngestRequest(),
    db: Session = Depends(get_db),
    current_user=Depends(require_dev),
) -> CertIngestResponse:
    try:
        result = ingest_certificates_from_fs(
            db,
            org_id=current_user.org_id,
            dry_run=payload.dry_run,
            limit=payload.limit,
            prune_missing=payload.prune_missing,
            dedupe=payload.dedupe,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if not payload.dry_run:
        log_audit(
            db=db,
            org_id=current_user.org_id,
            action="CERT_INGEST_FROM_FS",
            entity_type="certificate",
            entity_id=None,
            actor_user_id=current_user.id,
            meta={
                "inserted": result["inserted"],
                "updated": result["updated"],
                "failed": result["failed"],
                "total": result["total"],
                "pruned": result["pruned"],
                "deduped": result["deduped"],
                "limit": payload.limit,
            },
        )
        db.commit()

    return CertIngestResponse(**result)
