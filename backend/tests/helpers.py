import uuid

from sqlalchemy.orm import Session

from app import models
from app.core.security import ALLOWED_ROLES


def create_user(
    db: Session, role: str = "VIEW", auto_approve: bool = False, org_id: int = 1
) -> models.User:
    assert role in ALLOWED_ROLES
    user = models.User(
        org_id=org_id,
        ad_username=f"user_{role.lower()}_{uuid.uuid4().hex[:6]}",
        role_global=role,
        auto_approve_install_jobs=auto_approve,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_device(
    db: Session,
    *,
    auto_approve: bool = False,
    allow_keep_until: bool = True,
    allow_exempt: bool = True,
) -> models.Device:
    device = models.Device(
        org_id=1,
        hostname=f"device-{uuid.uuid4().hex[:6]}",
        auto_approve=auto_approve,
        allow_keep_until=allow_keep_until,
        allow_exempt=allow_exempt,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def create_certificate(db: Session, *, name: str | None = None, **kwargs) -> models.Certificate:
    cert = models.Certificate(org_id=1, name=name or f"Cert {uuid.uuid4().hex[:4]}", **kwargs)
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


def headers(user: models.User) -> dict[str, str]:
    return {"X-User-Id": str(user.id), "X-Org-Id": str(user.org_id)}
