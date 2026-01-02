from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import require_view_or_higher
from app.db.session import get_db
from app.models import Device, UserDevice
from app.schemas.device import DeviceRead

router = APIRouter(prefix="/devices", tags=["devices"])


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
