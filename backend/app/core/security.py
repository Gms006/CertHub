from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable

import jwt
from fastapi import Depends, Header, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import Device, User

ALLOWED_ROLES = {"DEV", "ADMIN", "VIEW"}
DEVICE_ROLE = "DEVICE"
AUTH_TOKEN_PURPOSE_SET_PASSWORD = "SET_PASSWORD"
AUTH_TOKEN_PURPOSE_RESET_PASSWORD = "RESET_PASSWORD"
BCRYPT_MAX_PASSWORD_BYTES = 72

http_bearer = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.bcrypt_cost)


def _ensure_role(user: User, allowed: Iterable[str]) -> None:
    if user.role_global not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _validate_password_length(password: str) -> None:
    if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="password must be at most 72 bytes",
        )


def hash_password(password: str) -> str:
    _validate_password_length(password)
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.access_token_ttl_min)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role_global": user.role_global,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_device_access_token(device: Device) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.device_token_ttl_min)
    payload = {
        "sub": str(device.id),
        "role": DEVICE_ROLE,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc


def decode_device_token(token: str) -> dict:
    payload = decode_access_token(token)
    if payload.get("role") != DEVICE_ROLE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid device token")
    return payload


def _get_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid authorization"
        )
    return token


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Security(http_bearer),
    x_org_id: int | None = Header(default=None, alias="X-Org-Id"),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
) -> User:
    token = credentials.credentials if credentials else _get_bearer_token(
        request.headers.get("Authorization") if request else None
    )
    if token:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
        user = db.get(User, uuid.UUID(user_id))
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid user")
    elif settings.allow_legacy_headers and settings.env.lower() == "dev":
        if x_user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing user")
        org_id = x_org_id or 1
        user = db.get(User, x_user_id)
        if user is None or user.org_id != org_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid user")
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="inactive user")
    if user.role_global not in ALLOWED_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid role")
    return user


async def require_view_or_higher(current_user: User = Depends(get_current_user)) -> User:
    _ensure_role(current_user, ALLOWED_ROLES)
    return current_user


async def require_admin_or_dev(current_user: User = Depends(get_current_user)) -> User:
    _ensure_role(current_user, {"ADMIN", "DEV"})
    return current_user


async def require_dev(current_user: User = Depends(get_current_user)) -> User:
    _ensure_role(current_user, {"DEV"})
    return current_user


async def require_device(
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Security(http_bearer),
) -> Device:
    token = credentials.credentials if credentials else _get_bearer_token(
        request.headers.get("Authorization") if request else None
    )
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    payload = decode_device_token(token)
    device_id = payload.get("sub")
    if not device_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    device = db.get(Device, uuid.UUID(device_id))
    if device is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid device")
    if not device.is_allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="device blocked")
    return device
