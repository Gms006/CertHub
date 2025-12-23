import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


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
