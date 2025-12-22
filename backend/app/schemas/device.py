import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeviceBase(BaseModel):
    hostname: str
    domain: str | None = None
    os_version: str | None = None
    agent_version: str | None = None
    last_seen_at: datetime | None = None
    is_allowed: bool = True


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    is_allowed: bool | None = None


class DeviceRead(DeviceBase):
    id: uuid.UUID
    org_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
