from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import status

from app import models
from app.core.security import create_device_access_token, hash_token
from tests.helpers import create_user, headers


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
    user = create_user(db, role="ADMIN")
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
        claimed_at=datetime.now(timezone.utc) if status_value != models.JOB_STATUS_PENDING else None,
        started_at=datetime.now(timezone.utc) if status_value != models.JOB_STATUS_PENDING else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return user, cert, job


def _auth_headers_for_device(device: models.Device):
    token = create_device_access_token(device)
    return {"Authorization": f"Bearer {token}"}


def test_result_duplicate_is_idempotent(test_client_and_session, tmp_path):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    device, _ = _create_device(db)
    _, _, job = _create_job(db, device, tmp_path, models.JOB_STATUS_IN_PROGRESS)

    response = client.post(
        f"/api/v1/agent/jobs/{job.id}/result",
        headers=_auth_headers_for_device(device),
        json={"status": "DONE", "thumbprint": "abc123"},
    )
    assert response.status_code == status.HTTP_200_OK

    db.refresh(job)
    finished_at = job.finished_at
    assert job.status == models.JOB_STATUS_DONE
    assert finished_at is not None

    duplicate = client.post(
        f"/api/v1/agent/jobs/{job.id}/result",
        headers=_auth_headers_for_device(device),
        json={"status": "DONE", "thumbprint": "abc123"},
    )
    assert duplicate.status_code == status.HTTP_409_CONFLICT
    db.refresh(job)
    assert job.status == models.JOB_STATUS_DONE
    assert job.finished_at == finished_at

    audit = (
        db.query(models.AuditLog)
        .filter_by(action="RESULT_DUPLICATE", entity_type="cert_install_job")
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )
    assert audit
    assert audit.meta_json["status"] == models.JOB_STATUS_DONE


def test_reap_stale_in_progress_jobs(test_client_and_session, tmp_path):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    device, _ = _create_device(db)
    admin_user = create_user(db, role="ADMIN")
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
        requested_by_user_id=admin_user.id,
        status=models.JOB_STATUS_IN_PROGRESS,
        claimed_by_device_id=device.id,
        claimed_at=datetime.now(timezone.utc) - timedelta(hours=2),
        started_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    response = client.post(
        "/api/v1/admin/jobs/reap?threshold_minutes=60",
        headers=headers(admin_user),
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["reaped"] == 1

    db.refresh(job)
    assert job.status == models.JOB_STATUS_FAILED
    assert job.finished_at is not None
    assert job.error_code == "TIMEOUT"

    audit = (
        db.query(models.AuditLog)
        .filter_by(action="JOB_REAPED", entity_type="cert_install_job")
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )
    assert audit
    assert audit.meta_json["job_id"] == str(job.id)
