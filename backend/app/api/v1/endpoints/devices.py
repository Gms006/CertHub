from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import log_audit
from app.core.security import require_view_or_higher
from app.db.session import get_db
from app.models import (
    CertInstallJob,
    Device,
    DeviceInstalledCert,
    JOB_STATUS_PENDING,
    JOB_TYPE_REMOVE,
    UserDevice,
)
from app.schemas.device import DeviceRead
from app.schemas.installed_cert import InstalledCertRead, InstalledCertRemoveResponse

router = APIRouter(prefix="/devices", tags=["devices"])


class InstalledCertScope(str, Enum):
    ALL = "all"
    AGENT = "agent"


@router.get("/mine", response_model=list[DeviceRead])
def list_my_devices(
    db: Session = Depends(get_db), current_user=Depends(require_view_or_higher)
) -> list[Device]:
    allowed_devices = (
        select(UserDevice.device_id)
        .where(
            UserDevice.user_id == current_user.id,
            UserDevice.is_allowed.is_(True),
        )
        .subquery()
    )
    statement = (
        select(Device)
        .where(Device.org_id == current_user.org_id)
        .where(
            or_(
                Device.assigned_user_id == current_user.id,
                Device.id.in_(select(allowed_devices.c.device_id)),
            )
        )
        .options(selectinload(Device.assigned_user))
        .order_by(Device.created_at)
    )
    return db.execute(statement).scalars().all()


@router.get("/{device_id}/installed-certs", response_model=list[InstalledCertRead])
def list_device_installed_certs(
    device_id: uuid.UUID,
    scope: InstalledCertScope = Query(default=InstalledCertScope.ALL),
    include_removed: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user=Depends(require_view_or_higher),
) -> list[DeviceInstalledCert]:
    device = db.get(Device, device_id)
    if device is None or device.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")

    # --- AUTHZ GATE (regressão) ---
    # Regra:
    # - ADMIN/DEV: permitido
    # - caso contrário: permitido somente se
    #   (device.assigned_user_id == current_user.id) OU
    #   existir UserDevice(device_id, user_id, is_allowed=True)
    if current_user.role_global not in {"ADMIN", "DEV"}:
        is_owner = device.assigned_user_id == current_user.id
        if not is_owner:
            has_explicit_allow = db.execute(
                select(UserDevice.user_id)
                .where(
                    UserDevice.device_id == device_id,
                    UserDevice.user_id == current_user.id,
                    UserDevice.is_allowed.is_(True),
                )
                .limit(1)
            ).scalar_one_or_none()
            if has_explicit_allow is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden",
                )
    # --- /AUTHZ GATE ---

    # TODO(manual-validate): validar authz do endpoint:
    # 1) VIEW sem permissão -> 403
    #    curl -i -H "Authorization: Bearer $TOKEN_VIEW" \
    #      "$BASE_URL/api/v1/devices/$DEVICE_OTHER/installed-certs?scope=all&include_removed=false"
    # 2) VIEW com UserDevice.is_allowed=true -> 200
    #    (crie/ajuste a permissão via endpoint/admin do portal ou via SQL) e repita o curl acima.
    # 3) ADMIN/DEV -> 200 para qualquer device da org
    #    curl -i -H "Authorization: Bearer $TOKEN_ADMIN" \
    #      "$BASE_URL/api/v1/devices/$DEVICE_OTHER/installed-certs?scope=all&include_removed=false"

    statement = select(DeviceInstalledCert).where(
        DeviceInstalledCert.org_id == current_user.org_id,
        DeviceInstalledCert.device_id == device_id,
    )
    if scope == InstalledCertScope.AGENT:
        statement = statement.where(DeviceInstalledCert.installed_via_agent.is_(True))
    if not include_removed:
        statement = statement.where(DeviceInstalledCert.removed_at.is_(None))
    statement = statement.order_by(
        DeviceInstalledCert.last_seen_at.desc(),
        DeviceInstalledCert.subject,
    )
    return db.execute(statement).scalars().all()


def _normalize_thumbprint(value: str) -> str:
    return value.replace(" ", "").upper()


@router.post(
    "/{device_id}/installed-certs/{thumbprint}/remove",
    response_model=InstalledCertRemoveResponse,
)
def remove_device_installed_cert(
    device_id: uuid.UUID,
    thumbprint: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_view_or_higher),
) -> InstalledCertRemoveResponse:
    device = db.get(Device, device_id)
    if device is None or device.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")

    if current_user.role_global not in {"ADMIN", "DEV"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    normalized = _normalize_thumbprint(thumbprint)
    entry = db.execute(
        select(DeviceInstalledCert)
        .where(
            DeviceInstalledCert.org_id == current_user.org_id,
            DeviceInstalledCert.device_id == device_id,
            DeviceInstalledCert.thumbprint == normalized,
        )
        .limit(1)
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="certificate not found")
    if entry.removed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="certificate already removed")
    if not entry.installed_via_agent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only agent-installed certificates can be removed",
        )

    now = datetime.now(timezone.utc)
    job = CertInstallJob(
        org_id=current_user.org_id,
        cert_id=None,
        device_id=device.id,
        requested_by_user_id=current_user.id,
        status=JOB_STATUS_PENDING,
        approved_by_user_id=current_user.id,
        approved_at=now,
        job_type=JOB_TYPE_REMOVE,
        target_thumbprint=normalized,
    )
    db.add(job)
    db.flush()
    log_audit(
        db=db,
        org_id=current_user.org_id,
        action="CERT_REMOVE_REQUESTED",
        entity_type="cert_install_job",
        entity_id=job.id,
        actor_user_id=current_user.id,
        meta={
            "job_id": str(job.id),
            "device_id": str(device.id),
            "thumbprint_last6": normalized[-6:] if len(normalized) > 6 else normalized,
        },
    )
    db.commit()
    return InstalledCertRemoveResponse(job_id=job.id)
