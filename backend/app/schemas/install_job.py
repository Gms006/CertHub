import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

JobStatus = Literal[
    "REQUESTED",
    "PENDING",
    "IN_PROGRESS",
    "DONE",
    "FAILED",
    "EXPIRED",
    "CANCELED",
]

CleanupMode = Literal["DEFAULT", "KEEP_UNTIL", "EXEMPT"]


class InstallJobCreate(BaseModel):
    device_id: uuid.UUID
    cleanup_mode: CleanupMode = "DEFAULT"
    keep_until: datetime | None = None
    keep_reason: str | None = None

    @model_validator(mode="after")
    def validate_retention_policy(self):
        if self.cleanup_mode == "KEEP_UNTIL" and self.keep_until is None:
            raise ValueError("keep_until is required when cleanup_mode is KEEP_UNTIL")
        if self.cleanup_mode == "EXEMPT" and not self.keep_reason:
            raise ValueError("keep_reason is required when cleanup_mode is EXEMPT")
        return self


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
    claimed_by_device_id: uuid.UUID | None
    claimed_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    thumbprint: str | None
    cleanup_mode: CleanupMode
    keep_until: datetime | None
    keep_reason: str | None
    keep_set_by_user_id: uuid.UUID | None
    keep_set_at: datetime | None
    status: JobStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
