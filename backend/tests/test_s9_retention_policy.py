from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import status

from app import models
from app.core.security import create_device_access_token, hash_token
from tests.helpers import create_certificate, create_device, create_user, headers


def _allow_view_on_device(db, user: models.User, device: models.Device) -> None:
    db.add(
        models.UserDevice(
            user_id=user.id,
            device_id=device.id,
            is_allowed=True,
        )
    )
    db.commit()


def test_view_can_set_keep_until_within_limit(test_client_and_session):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    user = create_user(db, role="VIEW")
    device = create_device(db)
    _allow_view_on_device(db, user, device)
    cert = create_certificate(db)
    keep_until = datetime.now(timezone.utc) + timedelta(hours=2)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        headers=headers(user),
        json={
            "device_id": str(device.id),
            "cleanup_mode": "KEEP_UNTIL",
            "keep_until": keep_until.isoformat(),
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    assert payload["cleanup_mode"] == "KEEP_UNTIL"

    job = db.get(models.CertInstallJob, uuid.UUID(payload["id"]))
    assert job is not None
    assert job.keep_until is not None
    assert job.keep_set_by_user_id == user.id

    audit = (
        db.query(models.AuditLog)
        .filter_by(action="RETENTION_SET", entity_type="cert_install_job", entity_id=str(job.id))
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )
    assert audit
    assert audit.meta_json["cleanup_mode"] == "KEEP_UNTIL"


def test_view_keep_until_outside_limit_is_rejected(test_client_and_session):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    user = create_user(db, role="VIEW")
    device = create_device(db)
    _allow_view_on_device(db, user, device)
    cert = create_certificate(db)
    keep_until = datetime.now(timezone.utc) + timedelta(hours=48)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        headers=headers(user),
        json={
            "device_id": str(device.id),
            "cleanup_mode": "KEEP_UNTIL",
            "keep_until": keep_until.isoformat(),
        },
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_view_exempt_is_forbidden(test_client_and_session):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    user = create_user(db, role="VIEW")
    device = create_device(db)
    _allow_view_on_device(db, user, device)
    cert = create_certificate(db)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        headers=headers(user),
        json={
            "device_id": str(device.id),
            "cleanup_mode": "EXEMPT",
            "keep_reason": "Fechamento fiscal",
        },
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_admin_can_exempt_with_reason(test_client_and_session):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    user = create_user(db, role="ADMIN")
    device = create_device(db)
    cert = create_certificate(db)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        headers=headers(user),
        json={
            "device_id": str(device.id),
            "cleanup_mode": "EXEMPT",
            "keep_reason": "Fechamento fiscal",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    assert payload["cleanup_mode"] == "EXEMPT"


def test_agent_payload_includes_retention_fields(test_client_and_session, tmp_path):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    device_token = "device-token"
    device = create_device(db)
    device.device_token_hash = hash_token(device_token)
    db.commit()

    cert_path = tmp_path / "cert_senha 123.pfx"
    cert_path.write_bytes(b"dummy-pfx")
    cert = create_certificate(db, source_path=str(cert_path))

    job = models.CertInstallJob(
        org_id=1,
        cert_id=cert.id,
        device_id=device.id,
        requested_by_user_id=create_user(db, role="ADMIN").id,
        status=models.JOB_STATUS_IN_PROGRESS,
        claimed_by_device_id=device.id,
        claimed_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        cleanup_mode=models.CLEANUP_MODE_KEEP_UNTIL,
        keep_until=datetime.now(timezone.utc) + timedelta(hours=1),
        keep_reason=None,
    )
    payload_token = "payload-token"
    job.payload_token_hash = hash_token(payload_token)
    job.payload_token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    job.payload_token_device_id = device.id
    db.add(job)
    db.commit()
    db.refresh(job)

    response = client.get(
        f"/api/v1/agent/jobs/{job.id}/payload?token={payload_token}",
        headers={"Authorization": f"Bearer {create_device_access_token(device)}"},
    )
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["cleanup_mode"] == "KEEP_UNTIL"
    assert payload["keep_until"] is not None
