from __future__ import annotations

import uuid
from typing import Iterable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User

ALLOWED_ROLES = {"DEV", "ADMIN", "VIEW"}


def _ensure_role(user: User, allowed: Iterable[str]) -> None:
    if user.role_global not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


async def get_current_user(
    db: Session = Depends(get_db),
    x_org_id: int | None = Header(default=None, alias="X-Org-Id"),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
) -> User:
    if x_user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing user")

    org_id = x_org_id or 1
    user = db.get(User, x_user_id)
    if user is None or user.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid user")
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
