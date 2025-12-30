from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import status

from app import models
from app.core.security import create_access_token, create_device_access_token, hash_token


def _create_device(db, *, allowed: bool = True):
    device_token = "device-token"
    device = models.Device(
        org_id=1,
        hostname=f"device-test-{uuid.uuid4().hex[:6]}",
        is_allowed=allowed,
        device_token_hash=hash_token(device_token),
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device, device_token


def _create_job(db, device: models.Device, tmp_path, status_value: str):
    user = models.User(org_id=1, ad_username="user_view", role_global="VIEW")
    db.add(user)
    db.commit()
    db.refresh(user)

    cert_path = tmp_path / "cert_senha 123.pfx"
    cert_path.write_bytes(b"dummy-pfx")
    cert = models.Certificate(org_id=1, name="Cert", source_path=str(cert_path))
    db.add(cert)
    db.commit()
    db.refresh(cert)

    job = models.CertInstallJob(
        org_id=1,
        cert_id=cert.id,
        device_id=device.id,
        requested_by_user_id=user.id,
        status=status_value,
        claimed_by_device_id=device.id if status_value != models.JOB_STATUS_PENDING else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return user, cert, job


def _auth_headers_for_device(device: models.Device):
    token = create_device_access_token(device)
    return {"Authorization": f"Bearer {token}"}


def _auth_headers_for_user(user: models.User):
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def test_payload_rejects_user_jwt(test_client_and_session, tmp_path):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    device, _ = _create_device(db)
    user, _, job = _create_job(db, device, tmp_path, models.JOB_STATUS_IN_PROGRESS)

    response = client.get(
        f"/api/v1/agent/jobs/{job.id}/payload",
        headers=_auth_headers_for_user(user),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_payload_requires_token(test_client_and_session, tmp_path):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    device, _ = _create_device(db)
    _, _, job = _create_job(db, device, tmp_path, models.JOB_STATUS_PENDING)

    claim_response = client.post(
        f"/api/v1/agent/jobs/{job.id}/claim",
        headers=_auth_headers_for_device(device),
        json={},
    )
    assert claim_response.status_code == status.HTTP_200_OK

    response = client.get(
        f"/api/v1/agent/jobs/{job.id}/payload",
        headers=_auth_headers_for_device(device),
    )

    assert response.status_code == status.HTTP_428_PRECONDITION_REQUIRED


def test_payload_token_single_use(test_client_and_session, tmp_path):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    device, _ = _create_device(db)
    _, _, job = _create_job(db, device, tmp_path, models.JOB_STATUS_PENDING)

    claim_response = client.post(
        f"/api/v1/agent/jobs/{job.id}/claim",
        headers=_auth_headers_for_device(device),
        json={},
    )
    payload_token = claim_response.json()["payload_token"]

    response = client.get(
        f"/api/v1/agent/jobs/{job.id}/payload?token={payload_token}",
        headers=_auth_headers_for_device(device),
    )
    assert response.status_code == status.HTTP_200_OK

    reuse = client.get(
        f"/api/v1/agent/jobs/{job.id}/payload?token={payload_token}",
        headers=_auth_headers_for_device(device),
    )
    assert reuse.status_code == status.HTTP_409_CONFLICT
    audit = (
        db.query(models.AuditLog)
        .filter_by(action="PAYLOAD_DENIED")
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )
    assert audit
    assert audit.meta_json["reason"] == "token_used"


def test_payload_token_expired(test_client_and_session, tmp_path):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    device, _ = _create_device(db)
    _, _, job = _create_job(db, device, tmp_path, models.JOB_STATUS_PENDING)

    claim_response = client.post(
        f"/api/v1/agent/jobs/{job.id}/claim",
        headers=_auth_headers_for_device(device),
        json={},
    )
    payload_token = claim_response.json()["payload_token"]

    job.payload_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    response = client.get(
        f"/api/v1/agent/jobs/{job.id}/payload?token={payload_token}",
        headers=_auth_headers_for_device(device),
    )
    assert response.status_code == status.HTTP_410_GONE
    audit = (
        db.query(models.AuditLog)
        .filter_by(action="PAYLOAD_DENIED")
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )
    assert audit
    assert audit.meta_json["reason"] == "token_expired"


def test_payload_device_mismatch(test_client_and_session, tmp_path):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    device, _ = _create_device(db)
    other_device, _ = _create_device(db)
    _, _, job = _create_job(db, device, tmp_path, models.JOB_STATUS_PENDING)

    claim_response = client.post(
        f"/api/v1/agent/jobs/{job.id}/claim",
        headers=_auth_headers_for_device(device),
        json={},
    )
    payload_token = claim_response.json()["payload_token"]

    response = client.get(
        f"/api/v1/agent/jobs/{job.id}/payload?token={payload_token}",
        headers=_auth_headers_for_device(other_device),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_payload_token_ttl_and_mismatch(test_client_and_session, tmp_path):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    device, _ = _create_device(db)
    _, _, job = _create_job(db, device, tmp_path, models.JOB_STATUS_PENDING)

    before = datetime.now(timezone.utc)
    claim_response = client.post(
        f"/api/v1/agent/jobs/{job.id}/claim",
        headers=_auth_headers_for_device(device),
        json={},
    )
    assert claim_response.status_code == status.HTTP_200_OK

    db.refresh(job)
    expires_at = job.payload_token_expires_at
    assert expires_at is not None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    delta = (expires_at - before).total_seconds()
    assert 115 <= delta <= 125

    response = client.get(
        f"/api/v1/agent/jobs/{job.id}/payload?token=wrong-token",
        headers=_auth_headers_for_device(device),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    audit = (
        db.query(models.AuditLog)
        .filter_by(action="PAYLOAD_DENIED")
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )
    assert audit
    assert audit.meta_json["reason"] == "token_mismatch"


def test_payload_rate_limit(test_client_and_session, tmp_path, monkeypatch):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    device, _ = _create_device(db)
    _, _, job = _create_job(db, device, tmp_path, models.JOB_STATUS_PENDING)

    def _deny_rate_limit(*_args, **_kwargs):
        return False, 99

    monkeypatch.setattr("app.api.v1.endpoints.agent.check_rate_limit", _deny_rate_limit)

    response = client.get(
        f"/api/v1/agent/jobs/{job.id}/payload?token=ignored",
        headers=_auth_headers_for_device(device),
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    audit = db.query(models.AuditLog).filter_by(action="PAYLOAD_RATE_LIMITED").all()
    assert audit


def test_claim_refreshes_token_for_in_progress_job(test_client_and_session, tmp_path):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    device, _ = _create_device(db)
    _, _, job = _create_job(db, device, tmp_path, models.JOB_STATUS_PENDING)

    first_claim = client.post(
        f"/api/v1/agent/jobs/{job.id}/claim",
        headers=_auth_headers_for_device(device),
        json={},
    )
    assert first_claim.status_code == status.HTTP_200_OK
    token_one = first_claim.json()["payload_token"]

    second_claim = client.post(
        f"/api/v1/agent/jobs/{job.id}/claim",
        headers=_auth_headers_for_device(device),
        json={},
    )
    assert second_claim.status_code == status.HTTP_200_OK
    token_two = second_claim.json()["payload_token"]
    assert token_two != token_one

    old_token_response = client.get(
        f"/api/v1/agent/jobs/{job.id}/payload?token={token_one}",
        headers=_auth_headers_for_device(device),
    )
    assert old_token_response.status_code == status.HTTP_403_FORBIDDEN

    response = client.get(
        f"/api/v1/agent/jobs/{job.id}/payload?token={token_two}",
        headers=_auth_headers_for_device(device),
    )
    assert response.status_code == status.HTTP_200_OK
