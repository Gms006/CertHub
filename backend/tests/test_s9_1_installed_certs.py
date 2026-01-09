from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import status

from app import models
from app.core.security import create_device_access_token
from tests.helpers import create_user, headers


def _auth_headers_for_device(device: models.Device) -> dict[str, str]:
    token = create_device_access_token(device)
    return {"Authorization": f"Bearer {token}"}


def _create_device(db, *, allowed: bool = True) -> models.Device:
    device = models.Device(
        org_id=1,
        hostname=f"device-{uuid.uuid4().hex[:6]}",
        is_allowed=allowed,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def test_report_upsert_and_removed_marking(test_client_and_session):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    device = _create_device(db)
    payload = {
        "device_id": str(device.id),
        "items": [
            {
                "thumbprint": "AAA111",
                "subject": "CN=Alpha",
                "issuer": "CN=Issuer",
                "serial": "01",
                "installed_via_agent": True,
                "cleanup_mode": "DEFAULT",
            },
            {
                "thumbprint": "BBB222",
                "subject": "CN=Beta",
                "issuer": "CN=Issuer",
                "serial": "02",
                "installed_via_agent": False,
            },
        ],
    }
    response = client.post(
        "/api/v1/agent/installed-certs/report",
        headers=_auth_headers_for_device(device),
        json=payload,
    )
    assert response.status_code == status.HTTP_200_OK

    entries = (
        db.query(models.DeviceInstalledCert)
        .filter_by(device_id=device.id)
        .order_by(models.DeviceInstalledCert.thumbprint)
        .all()
    )
    assert len(entries) == 2
    assert all(entry.removed_at is None for entry in entries)

    response = client.post(
        "/api/v1/agent/installed-certs/report",
        headers=_auth_headers_for_device(device),
        json={
            "device_id": str(device.id),
            "items": [
                {
                    "thumbprint": "AAA111",
                    "subject": "CN=Alpha",
                    "issuer": "CN=Issuer",
                    "serial": "01",
                    "installed_via_agent": True,
                    "cleanup_mode": "DEFAULT",
                }
            ],
        },
    )
    assert response.status_code == status.HTTP_200_OK

    db.expire_all()
    removed = (
        db.query(models.DeviceInstalledCert)
        .filter_by(device_id=device.id, thumbprint="BBB222")
        .one()
    )
    assert removed.removed_at is not None


def test_scope_agent_filters_non_agent_entries(test_client_and_session):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    admin_user = create_user(db, role="ADMIN")
    device = _create_device(db)
    db.add(
        models.DeviceInstalledCert(
            org_id=1,
            device_id=device.id,
            thumbprint="AAA111",
            subject="CN=Alpha",
            installed_via_agent=True,
            cleanup_mode="DEFAULT",
            last_seen_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        models.DeviceInstalledCert(
            org_id=1,
            device_id=device.id,
            thumbprint="BBB222",
            subject="CN=Beta",
            installed_via_agent=False,
            last_seen_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    response = client.get(
        f"/api/v1/devices/{device.id}/installed-certs?scope=agent",
        headers=headers(admin_user),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["thumbprint"] == "AAA111"


def test_view_user_forbidden_for_unassigned_device(test_client_and_session):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    view_user = create_user(db, role="VIEW")
    device = _create_device(db)

    response = client.get(
        f"/api/v1/devices/{device.id}/installed-certs",
        headers=headers(view_user),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
