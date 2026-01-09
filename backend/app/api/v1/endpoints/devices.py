from __future__ import annotations

import uuid
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import require_view_or_higher
from app.db.session import get_db
from app.models import Device, DeviceInstalledCert, UserDevice
from app.schemas.device import DeviceRead
from app.schemas.installed_cert import InstalledCertRead

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

    if current_user.role_global not in {"ADMIN", "DEV"}:
        allowed = db.execute(
            select(UserDevice)
            .where(
                UserDevice.device_id == device_id,
                UserDevice.user_id == current_user.id,
                UserDevice.is_allowed.is_(True),
            )
            .limit(1)
        ).scalar_one_or_none()
        if device.assigned_user_id != current_user.id and allowed is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

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
