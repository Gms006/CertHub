import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CertificateBase(BaseModel):
    name: str


class CertificateCreate(CertificateBase):
    pass


class CertificateRead(CertificateBase):
    id: uuid.UUID
    org_id: int
    subject: str | None = None
    issuer: str | None = None
    serial_number: str | None = None
    sha1_fingerprint: str | None = None
    parse_error: str | None = None
    source_path: str | None = None
    parse_ok: bool
    last_ingested_at: datetime | None = None
    last_error_at: datetime | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
