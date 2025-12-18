import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

JobStatus = Literal[
    "REQUESTED",
    "PENDING",
    "IN_PROGRESS",
    "DONE",
    "FAILED",
    "EXPIRED",
    "CANCELED",
]


class InstallJobCreate(BaseModel):
    device_id: uuid.UUID


class InstallJobApproveRequest(BaseModel):
    reason: str | None = None


class InstallJobRead(BaseModel):
    id: uuid.UUID
    org_id: int
    cert_id: uuid.UUID
    device_id: uuid.UUID
    requested_by_user_id: uuid.UUID
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    status: JobStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
