import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.core.security import ALLOWED_ROLES  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def test_client_and_session():
    engine = create_engine(
        os.environ["DATABASE_URL"], connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, class_=Session, expire_on_commit=False
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _create_user(db: Session, role: str = "VIEW", auto_approve: bool = False) -> models.User:
    assert role in ALLOWED_ROLES
    user = models.User(
        org_id=1,
        ad_username=f"user_{role.lower()}_{uuid.uuid4().hex[:6]}",
        role_global=role,
        auto_approve_install_jobs=auto_approve,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_device(db: Session) -> models.Device:
    device = models.Device(org_id=1, hostname=f"device-{uuid.uuid4().hex[:6]}")
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def _create_certificate(db: Session) -> models.Certificate:
    cert = models.Certificate(org_id=1, name=f"Cert {uuid.uuid4().hex[:4]}")
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


def _headers(user: models.User) -> dict[str, str]:
    return {"X-User-Id": str(user.id), "X-Org-Id": str(user.org_id)}


def test_view_without_auto_approve_creates_requested(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        viewer = _create_user(db, role="VIEW", auto_approve=False)
        cert = _create_certificate(db)
        device = _create_device(db)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=_headers(viewer),
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == models.JOB_STATUS_REQUESTED
    assert payload["requested_by_user_id"] == str(viewer.id)


def test_view_with_auto_approve_creates_pending(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        viewer = _create_user(db, role="VIEW", auto_approve=True)
        cert = _create_certificate(db)
        device = _create_device(db)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=_headers(viewer),
    )
    assert response.status_code == 201
    assert response.json()["status"] == models.JOB_STATUS_PENDING


def test_admin_creates_pending_job(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        admin = _create_user(db, role="ADMIN")
        cert = _create_certificate(db)
        device = _create_device(db)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=_headers(admin),
    )
    assert response.status_code == 201
    assert response.json()["status"] == models.JOB_STATUS_PENDING


def test_admin_approves_requested_job(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        admin = _create_user(db, role="ADMIN")
        viewer = _create_user(db, role="VIEW")
        cert = _create_certificate(db)
        device = _create_device(db)

    create_resp = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=_headers(viewer),
    )
    job_id = create_resp.json()["id"]

    approve_resp = client.post(
        f"/api/v1/install-jobs/{job_id}/approve",
        json={},
        headers=_headers(admin),
    )
    assert approve_resp.status_code == 200
    payload = approve_resp.json()
    assert payload["status"] == models.JOB_STATUS_PENDING
    assert payload["approved_by_user_id"] == str(admin.id)
    assert payload["approved_at"] is not None


def test_view_cannot_approve_job(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        viewer = _create_user(db, role="VIEW")
        cert = _create_certificate(db)
        device = _create_device(db)

    create_resp = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=_headers(viewer),
    )
    job_id = create_resp.json()["id"]

    deny_resp = client.post(
        f"/api/v1/install-jobs/{job_id}/approve",
        json={},
        headers=_headers(viewer),
    )
    assert deny_resp.status_code == 403


def test_view_listing_permissions(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        viewer = _create_user(db, role="VIEW")
        cert = _create_certificate(db)
        device = _create_device(db)

    create_resp = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=_headers(viewer),
    )
    assert create_resp.status_code == 201

    general_list = client.get("/api/v1/install-jobs", headers=_headers(viewer))
    assert general_list.status_code == 403

    mine_list = client.get("/api/v1/install-jobs?mine=true", headers=_headers(viewer))
    assert mine_list.status_code == 200
    mine_payload = mine_list.json()
    assert len(mine_payload) == 1
    assert mine_payload[0]["requested_by_user_id"] == str(viewer.id)
