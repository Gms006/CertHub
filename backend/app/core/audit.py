from __future__ import annotations

import uuid
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.models import AuditLog


def log_audit(
    db: Session,
    org_id: int,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_device_id: uuid.UUID | None = None,
    ip: str | None = None,
    meta: dict[str, Any] | None = None,
) -> AuditLog:
    """Persist an audit log entry using the provided database session."""

    audit = AuditLog(
        org_id=org_id,
        actor_user_id=actor_user_id,
        actor_device_id=actor_device_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        ip=ip,
        meta_json=jsonable_encoder(meta) if meta is not None else None,
    )
    db.add(audit)
    return audit
