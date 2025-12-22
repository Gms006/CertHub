from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.config import settings
from app.core.security import (
    AUTH_TOKEN_PURPOSE_RESET_PASSWORD,
    AUTH_TOKEN_PURPOSE_SET_PASSWORD,
    create_access_token,
    generate_token,
    get_current_user,
    hash_password,
    hash_token,
    require_admin_or_dev,
    verify_password,
)
from app.db.session import get_db
from app.models import AuthToken, User, UserSession
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    PasswordConfirmRequest,
    PasswordResetInitRequest,
    PasswordSetInitRequest,
    RefreshRequest,
    RefreshResponse,
    TokenInitResponse,
)
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"


def _get_refresh_token(request: Request, body: dict[str, Any] | None = None) -> str | None:
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if token:
        return token
    if body:
        return body.get("refresh_token")
    return None


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        httponly=settings.cookie_httponly,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite.lower(),
        max_age=settings.refresh_ttl_days * 24 * 60 * 60,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")


@router.post("/password/set/init", response_model=TokenInitResponse)
def password_set_init(
    payload: PasswordSetInitRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_dev),
) -> TokenInitResponse:
    statement = select(User).where(
        func.lower(User.email) == payload.email.lower(),
        User.org_id == current_user.org_id,
    )
    user = db.execute(statement).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    raw_token = generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.set_password_token_ttl_min
    )
    auth_token = AuthToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        purpose=AUTH_TOKEN_PURPOSE_SET_PASSWORD,
        expires_at=expires_at,
    )
    db.add(auth_token)
    db.commit()
    token_value = raw_token if settings.env.lower() == "dev" else None
    return TokenInitResponse(
        ok=True,
        token=token_value,
        expires_at=expires_at if token_value else None,
    )


@router.post("/password/set/confirm", response_model=MessageResponse)
def password_set_confirm(
    payload: PasswordConfirmRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    token_hash = hash_token(payload.token)
    statement = select(AuthToken).where(
        AuthToken.token_hash == token_hash,
        AuthToken.purpose == AUTH_TOKEN_PURPOSE_SET_PASSWORD,
        AuthToken.used_at.is_(None),
        AuthToken.expires_at >= datetime.now(timezone.utc),
    )
    auth_token = db.execute(statement).scalar_one_or_none()
    if auth_token is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid token")

    user = db.get(User, auth_token.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid token")

    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(payload.new_password)
    if user.password_set_at is None:
        user.password_set_at = now
    user.failed_login_attempts = 0
    user.locked_until = None
    auth_token.used_at = now
    db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == AUTH_TOKEN_PURPOSE_SET_PASSWORD,
            AuthToken.used_at.is_(None),
            AuthToken.id != auth_token.id,
        )
        .values(used_at=now)
    )
    log_audit(
        db=db,
        org_id=user.org_id,
        action="PASSWORD_SET",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
    )
    db.commit()
    return MessageResponse(message="password set")


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    statement = select(User).where(func.lower(User.email) == payload.email.lower())
    user = db.execute(statement).scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if user is None:
        log_audit(
            db=db,
            org_id=settings.default_org_id,
            action="LOGIN_FAILED",
            entity_type="user",
            entity_id=None,
            ip=request.client.host if request.client else None,
            meta={"reason": "user_not_found"},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    if not user.is_active:
        log_audit(
            db=db,
            org_id=user.org_id,
            action="LOGIN_FAILED",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            ip=request.client.host if request.client else None,
            meta={"reason": "inactive"},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="inactive user")

    if user.locked_until and user.locked_until > now:
        log_audit(
            db=db,
            org_id=user.org_id,
            action="LOGIN_LOCKED",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            ip=request.client.host if request.client else None,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many login attempts",
        )

    if not user.password_hash or not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        log_audit(
            db=db,
            org_id=user.org_id,
            action="LOGIN_FAILED",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            ip=request.client.host if request.client else None,
            meta={"reason": "invalid_password"},
        )
        if user.failed_login_attempts >= settings.lockout_max_attempts:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            log_audit(
                db=db,
                org_id=user.org_id,
                action="LOGIN_LOCKED",
                entity_type="user",
                entity_id=user.id,
                actor_user_id=user.id,
                ip=request.client.host if request.client else None,
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too many login attempts",
            )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    user.failed_login_attempts = 0
    user.locked_until = None
    access_token = create_access_token(user)
    refresh_token = generate_token()
    refresh_expires_at = now + timedelta(days=settings.refresh_ttl_days)
    session = UserSession(
        user_id=user.id,
        refresh_token_hash=hash_token(refresh_token),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        expires_at=refresh_expires_at,
    )
    db.add(session)
    log_audit(
        db=db,
        org_id=user.org_id,
        action="LOGIN_SUCCESS",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        ip=request.client.host if request.client else None,
    )
    db.commit()
    _set_refresh_cookie(response, refresh_token)
    return LoginResponse(
        access_token=access_token,
        refresh_token=None,
        user=UserRead.model_validate(user, from_attributes=True),
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh_token(
    request: Request,
    payload: RefreshRequest | None = None,
    db: Session = Depends(get_db),
) -> RefreshResponse:
    refresh_token_value = _get_refresh_token(
        request, payload.model_dump() if payload else None
    )
    if not refresh_token_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing refresh token")

    token_hash = hash_token(refresh_token_value)
    statement = select(UserSession).where(
        UserSession.refresh_token_hash == token_hash,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at >= datetime.now(timezone.utc),
    )
    session = db.execute(statement).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")

    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")

    access_token = create_access_token(user)
    return RefreshResponse(access_token=access_token)


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    payload: RefreshRequest | None = None,
) -> MessageResponse:
    refresh_token_value = _get_refresh_token(
        request, payload.model_dump() if payload else None
    )
    if refresh_token_value:
        token_hash = hash_token(refresh_token_value)
        statement = select(UserSession).where(
            UserSession.refresh_token_hash == token_hash,
            UserSession.user_id == current_user.id,
            UserSession.revoked_at.is_(None),
        )
        session = db.execute(statement).scalar_one_or_none()
        if session:
            session.revoked_at = datetime.now(timezone.utc)
    log_audit(
        db=db,
        org_id=current_user.org_id,
        action="LOGOUT",
        entity_type="user",
        entity_id=current_user.id,
        actor_user_id=current_user.id,
        ip=request.client.host if request.client else None,
    )
    db.commit()
    _clear_refresh_cookie(response)
    return MessageResponse(message="logout ok")


@router.post("/password/reset/init", response_model=TokenInitResponse)
def password_reset_init(
    payload: PasswordResetInitRequest,
    db: Session = Depends(get_db),
) -> TokenInitResponse:
    statement = select(User).where(func.lower(User.email) == payload.email.lower())
    user = db.execute(statement).scalar_one_or_none()
    raw_token = generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.reset_password_token_ttl_min
    )
    if user is not None:
        auth_token = AuthToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            purpose=AUTH_TOKEN_PURPOSE_RESET_PASSWORD,
            expires_at=expires_at,
        )
        db.add(auth_token)
        db.commit()
    token_value = raw_token if settings.env.lower() == "dev" else None
    return TokenInitResponse(
        ok=True,
        token=token_value,
        expires_at=expires_at if token_value else None,
    )


@router.post("/password/reset/confirm", response_model=MessageResponse)
def password_reset_confirm(
    payload: PasswordConfirmRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    token_hash = hash_token(payload.token)
    statement = select(AuthToken).where(
        AuthToken.token_hash == token_hash,
        AuthToken.purpose == AUTH_TOKEN_PURPOSE_RESET_PASSWORD,
        AuthToken.used_at.is_(None),
        AuthToken.expires_at >= datetime.now(timezone.utc),
    )
    auth_token = db.execute(statement).scalar_one_or_none()
    if auth_token is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid token")

    user = db.get(User, auth_token.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid token")

    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(payload.new_password)
    user.password_set_at = user.password_set_at or now
    user.failed_login_attempts = 0
    user.locked_until = None
    auth_token.used_at = now
    db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == AUTH_TOKEN_PURPOSE_RESET_PASSWORD,
            AuthToken.used_at.is_(None),
            AuthToken.id != auth_token.id,
        )
        .values(used_at=now)
    )
    log_audit(
        db=db,
        org_id=user.org_id,
        action="PASSWORD_RESET",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
    )
    db.commit()
    return MessageResponse(message="password reset")


@router.get("/me", response_model=UserRead)
def me(current_user=Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user, from_attributes=True)
