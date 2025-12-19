from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.user import UserRead


class PasswordSetInitRequest(BaseModel):
    email: str


class PasswordConfirmRequest(BaseModel):
    token: str
    new_password: str


class PasswordResetInitRequest(BaseModel):
    email: str


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: UserRead


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenInitResponse(BaseModel):
    ok: bool = True
    token: str | None = None
    expires_at: datetime | None = None


class MessageResponse(BaseModel):
    message: str
    token: str | None = None
    expires_at: datetime | None = None
