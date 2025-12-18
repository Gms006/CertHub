import uuid

import importlib.util
from pathlib import Path

helpers_path = Path(__file__).resolve().parent / "helpers.py"
helpers_spec = importlib.util.spec_from_file_location("tests.helpers", helpers_path)
helpers = importlib.util.module_from_spec(helpers_spec)
assert helpers_spec and helpers_spec.loader
helpers_spec.loader.exec_module(helpers)

from app import models
from app.models import AuditLog

create_certificate = helpers.create_certificate
create_device = helpers.create_device
create_user = helpers.create_user
headers = helpers.headers


def test_view_without_auto_approve_creates_requested(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        viewer = create_user(db, role="VIEW", auto_approve=False)
        cert = create_certificate(db)
        device = create_device(db)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=headers(viewer),
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == models.JOB_STATUS_REQUESTED
    assert payload["requested_by_user_id"] == str(viewer.id)


def test_view_with_auto_approve_creates_pending(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        viewer = create_user(db, role="VIEW", auto_approve=True)
        cert = create_certificate(db)
        device = create_device(db)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=headers(viewer),
    )
    assert response.status_code == 201
    assert response.json()["status"] == models.JOB_STATUS_PENDING


def test_auto_approve_flag_sets_approved_and_audit(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        viewer = create_user(db, role="VIEW", auto_approve=True)
        cert = create_certificate(db)
        device = create_device(db)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=headers(viewer),
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == models.JOB_STATUS_PENDING
    assert payload["approved_by_user_id"] == str(viewer.id)
    assert payload["approved_at"] is not None

    with SessionLocal() as db:
        audits = db.query(AuditLog).order_by(AuditLog.timestamp).all()
        assert [audit.action for audit in audits] == ["INSTALL_REQUESTED", "INSTALL_APPROVED"]
        assert audits[-1].meta_json == {
            "auto": True,
            "via": "flag",
            "job_id": payload["id"],
        }


def test_admin_creates_pending_job(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        admin = create_user(db, role="ADMIN")
        cert = create_certificate(db)
        device = create_device(db)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=headers(admin),
    )
    assert response.status_code == 201
    assert response.json()["status"] == models.JOB_STATUS_PENDING


def test_admin_auto_approval_sets_fields_and_audit(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        admin = create_user(db, role="ADMIN")
        cert = create_certificate(db)
        device = create_device(db)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=headers(admin),
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == models.JOB_STATUS_PENDING
    assert payload["approved_by_user_id"] == str(admin.id)
    assert payload["approved_at"] is not None

    with SessionLocal() as db:
        audits = db.query(AuditLog).order_by(AuditLog.timestamp).all()
        assert [audit.action for audit in audits] == ["INSTALL_REQUESTED", "INSTALL_APPROVED"]
        assert audits[-1].meta_json["via"] == "role"


def test_admin_approves_requested_job(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        admin = create_user(db, role="ADMIN")
        viewer = create_user(db, role="VIEW")
        cert = create_certificate(db)
        device = create_device(db)

    create_resp = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=headers(viewer),
    )
    job_id = create_resp.json()["id"]

    approve_resp = client.post(
        f"/api/v1/install-jobs/{job_id}/approve",
        json={},
        headers=headers(admin),
    )
    assert approve_resp.status_code == 200
    payload = approve_resp.json()
    assert payload["status"] == models.JOB_STATUS_PENDING
    assert payload["approved_by_user_id"] == str(admin.id)
    assert payload["approved_at"] is not None


def test_view_cannot_approve_job(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        viewer = create_user(db, role="VIEW")
        cert = create_certificate(db)
        device = create_device(db)

    create_resp = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=headers(viewer),
    )
    job_id = create_resp.json()["id"]

    deny_resp = client.post(
        f"/api/v1/install-jobs/{job_id}/approve",
        json={},
        headers=headers(viewer),
    )
    assert deny_resp.status_code == 403


def test_view_without_flag_does_not_auto_approve(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        viewer = create_user(db, role="VIEW", auto_approve=False)
        cert = create_certificate(db)
        device = create_device(db)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=headers(viewer),
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == models.JOB_STATUS_REQUESTED
    assert payload["approved_by_user_id"] is None
    assert payload["approved_at"] is None

    with SessionLocal() as db:
        audits = db.query(AuditLog).order_by(AuditLog.timestamp).all()
        assert len(audits) == 1
        assert audits[0].action == "INSTALL_REQUESTED"


def test_view_listing_permissions(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        viewer = create_user(db, role="VIEW")
        cert = create_certificate(db)
        device = create_device(db)

    create_resp = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id)},
        headers=headers(viewer),
    )
    assert create_resp.status_code == 201

    general_list = client.get("/api/v1/install-jobs", headers=headers(viewer))
    assert general_list.status_code == 403

    mine_list = client.get("/api/v1/install-jobs?mine=true", headers=headers(viewer))
    assert mine_list.status_code == 200
    mine_payload = mine_list.json()
    assert len(mine_payload) == 1
    assert mine_payload[0]["requested_by_user_id"] == str(viewer.id)
