import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.install_job import InstallJobRead


class AgentAuthRequest(BaseModel):
    device_id: uuid.UUID
    device_token: str


class AgentAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AgentHeartbeatRequest(BaseModel):
    agent_version: str | None = None


class AgentJobStatusUpdate(BaseModel):
    status: Literal["DONE", "FAILED"]
    thumbprint: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class AgentPayloadResponse(BaseModel):
    job_id: uuid.UUID
    cert_id: uuid.UUID
    pfx_base64: str
    password: str
    source_path: str
    generated_at: datetime
    cleanup_mode: Literal["DEFAULT", "KEEP_UNTIL", "EXEMPT"] | None = None
    keep_until: datetime | None = None
    keep_reason: str | None = None


class AgentCleanupEvent(BaseModel):
    removed_count: int
    failed_count: int
    removed_thumbprints: list[str] | None = None
    failed_thumbprints: list[str] | None = None
    skipped_count: int | None = None
    skipped_thumbprints: list[str] | None = None
    mode: Literal["scheduled", "fallback", "manual"]
    ran_at_local: str | None = None


class AgentJobClaimResponse(InstallJobRead):
    payload_token: str
