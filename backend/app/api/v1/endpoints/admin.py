from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.security import require_dev
from app.db.session import get_db
from app.models import Device, User, UserDevice, UserEmpresaPermission
from app.schemas.device import DeviceCreate, DeviceRead
from app.schemas.permission import UserEmpresaPermissionCreate, UserEmpresaPermissionRead
from app.schemas.user import UserCreate, UserRead
from app.schemas.user_device import UserDeviceCreate, UserDeviceRead

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_dev)])


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_dev),
) -> User:
    org_id = current_user.org_id
    user = User(org_id=org_id, **user_in.model_dump())
    db.add(user)
    log_audit(
        db=db,
        org_id=org_id,
        action="USER_CREATED",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=current_user.id,
        meta={"ad_username": user.ad_username},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.orig))
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db), current_user=Depends(require_dev)
) -> list[User]:
    statement = (
        select(User)
        .where(User.org_id == current_user.org_id)
        .order_by(User.created_at)
    )
    return db.execute(statement).scalars().all()


@router.post("/devices", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
def create_device(
    device_in: DeviceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_dev),
) -> Device:
    org_id = current_user.org_id
    device = Device(org_id=org_id, **device_in.model_dump())
    db.add(device)
    log_audit(
        db=db,
        org_id=org_id,
        action="DEVICE_CREATED",
        entity_type="device",
        entity_id=device.id,
        actor_user_id=current_user.id,
        meta={"hostname": device.hostname},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.orig))
    db.refresh(device)
    return device


@router.get("/devices", response_model=list[DeviceRead])
def list_devices(
    db: Session = Depends(get_db), current_user=Depends(require_dev)
) -> list[Device]:
    statement = (
        select(Device)
        .where(Device.org_id == current_user.org_id)
        .order_by(Device.created_at)
    )
    return db.execute(statement).scalars().all()


@router.post(
    "/user-devices",
    response_model=UserDeviceRead,
    status_code=status.HTTP_201_CREATED,
)
def link_user_device(
    payload: UserDeviceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_dev),
) -> UserDevice:
    link = UserDevice(**payload.model_dump())
    db.add(link)
    log_audit(
        db=db,
        org_id=current_user.org_id,
        action="USER_DEVICE_LINKED",
        entity_type="user_device",
        entity_id=f"{link.user_id}:{link.device_id}",
        actor_user_id=current_user.id,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.orig))
    db.refresh(link)
    return link


@router.post(
    "/permissions",
    response_model=UserEmpresaPermissionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_permission(
    payload: UserEmpresaPermissionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_dev),
) -> UserEmpresaPermission:
    permission = UserEmpresaPermission(org_id=current_user.org_id, **payload.model_dump())
    db.add(permission)
    log_audit(
        db=db,
        org_id=current_user.org_id,
        action="PERMISSION_CREATED",
        entity_type="user_empresa_permission",
        entity_id=permission.id,
        actor_user_id=current_user.id,
        meta={"role": permission.role, "empresa_id": str(permission.empresa_id)},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.orig))
    db.refresh(permission)
    return permission
