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
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
