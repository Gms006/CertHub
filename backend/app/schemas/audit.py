import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: uuid.UUID
    timestamp: datetime
    action: str
    entity_type: str
    entity_id: str | None = None
    actor_user_id: uuid.UUID | None = None
    actor_device_id: uuid.UUID | None = None
    actor_label: str | None = None
    meta_json: dict | None = None
