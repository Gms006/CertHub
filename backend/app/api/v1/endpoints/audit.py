from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_view_or_higher
from app.db.session import get_db
from app.models import AuditLog, Device, User
from app.schemas.audit import AuditLogRead

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(
    action: str | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(require_view_or_higher),
) -> list[AuditLogRead]:
    statement = (
        select(AuditLog, User, Device)
        .join(User, AuditLog.actor_user_id == User.id, isouter=True)
        .join(Device, AuditLog.actor_device_id == Device.id, isouter=True)
        .where(AuditLog.org_id == current_user.org_id)
    )
    if action:
        statement = statement.where(AuditLog.action == action)
    if actor_user_id:
        statement = statement.where(AuditLog.actor_user_id == actor_user_id)
    statement = statement.order_by(AuditLog.timestamp.desc()).limit(limit)
    results = db.execute(statement).all()

    payload: list[AuditLogRead] = []
    for audit, user, device in results:
        actor_label = None
        if user is not None:
            actor_label = user.nome or user.ad_username or user.email
        if actor_label is None and device is not None:
            actor_label = device.hostname
        payload.append(
            AuditLogRead(
                id=audit.id,
                timestamp=audit.timestamp,
                action=audit.action,
                entity_type=audit.entity_type,
                entity_id=audit.entity_id,
                actor_user_id=audit.actor_user_id,
                actor_device_id=audit.actor_device_id,
                actor_label=actor_label,
                meta_json=audit.meta_json,
            )
        )
    return payload
