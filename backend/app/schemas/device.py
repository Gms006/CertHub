import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserRead


class DeviceBase(BaseModel):
    hostname: str
    domain: str | None = None
    os_version: str | None = None
    agent_version: str | None = None
    last_seen_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    is_allowed: bool = True
    assigned_user_id: uuid.UUID | None = None


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    is_allowed: bool | None = None
    assigned_user_id: uuid.UUID | None = None


class DeviceRead(DeviceBase):
    id: uuid.UUID
    org_id: int
    created_at: datetime
    assigned_user: UserRead | None = None
    last_job_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DeviceCreateResponse(DeviceRead):
    device_token: str


class DeviceTokenRotateResponse(BaseModel):
    device_id: uuid.UUID
    device_token: str
    token_created_at: datetime
