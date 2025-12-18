import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    ad_username: str
    email: str | None = None
    nome: str | None = None
    is_active: bool = True
    role_global: str = "VIEW"
    auto_approve_install_jobs: bool = False


class UserCreate(UserBase):
    role_global: str = "VIEW"
    auto_approve_install_jobs: bool = False


class UserUpdate(BaseModel):
    ad_username: str | None = None
    email: str | None = None
    nome: str | None = None
    is_active: bool | None = None
    role_global: str | None = None
    auto_approve_install_jobs: bool | None = None


class UserRead(UserBase):
    id: uuid.UUID
    org_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
