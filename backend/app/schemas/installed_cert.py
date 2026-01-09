import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

CleanupMode = Literal["DEFAULT", "KEEP_UNTIL", "EXEMPT"]


class InstalledCertReportItem(BaseModel):
    thumbprint: str
    subject: str | None = None
    issuer: str | None = None
    serial: str | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None
    installed_via_agent: bool = False
    cleanup_mode: CleanupMode | None = None
    keep_until: datetime | None = None
    keep_reason: str | None = None
    job_id: uuid.UUID | None = None
    installed_at: datetime | None = None


class InstalledCertReportRequest(BaseModel):
    device_id: uuid.UUID | None = None
    items: list[InstalledCertReportItem]


class InstalledCertRead(BaseModel):
    device_id: uuid.UUID
    thumbprint: str
    subject: str | None
    issuer: str | None
    serial: str | None
    not_before: datetime | None
    not_after: datetime | None
    installed_via_agent: bool
    cleanup_mode: CleanupMode | None
    keep_until: datetime | None
    keep_reason: str | None
    job_id: uuid.UUID | None
    installed_at: datetime | None
    last_seen_at: datetime
    removed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
