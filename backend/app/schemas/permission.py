import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserEmpresaPermissionCreate(BaseModel):
    user_id: uuid.UUID
    empresa_id: uuid.UUID | None = None
    role: str
    is_allowed: bool = True


class UserEmpresaPermissionRead(UserEmpresaPermissionCreate):
    id: uuid.UUID
    org_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
