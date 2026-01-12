from __future__ import annotations

import uuid

from fastapi import status

from app import models
from app.core.security import create_access_token


def test_job_endpoints_do_not_expose_payload_fields(test_client_and_session, tmp_path):
    client, sessionmaker = test_client_and_session
    db = sessionmaker()

    user = models.User(org_id=1, ad_username="user_view", role_global="VIEW")
    db.add(user)
    db.commit()
    db.refresh(user)

    device = models.Device(
        org_id=1,
        hostname=f"device-{uuid.uuid4().hex[:6]}",
        assigned_user_id=user.id,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    cert_path = tmp_path / "cert_senha 123.pfx"
    cert_path.write_bytes(b"dummy-pfx")
    certificate = models.Certificate(
        org_id=1,
        name="Cert",
        source_path=str(cert_path),
    )
    db.add(certificate)
    db.commit()
    db.refresh(certificate)

    token = create_access_token(user)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        f"/api/v1/certificados/{certificate.id}/install",
        headers=headers,
        json={"device_id": str(device.id), "cleanup_mode": "DEFAULT"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    for key in ("pfx_base64", "password", "payload_token", "source_path"):
        assert key not in payload

    list_response = client.get("/api/v1/install-jobs/mine", headers=headers)
    assert list_response.status_code == status.HTTP_200_OK
    listed = list_response.json()
    assert listed
    for item in listed:
        for key in ("pfx_base64", "password", "payload_token", "source_path"):
            assert key not in item

    my_device_response = client.get("/api/v1/install-jobs/my-device", headers=headers)
    assert my_device_response.status_code == status.HTTP_200_OK
    my_device_listed = my_device_response.json()
    assert my_device_listed
    for item in my_device_listed:
        for key in ("pfx_base64", "password", "payload_token", "source_path"):
            assert key not in item

    admin_user = models.User(org_id=1, ad_username="user_admin", role_global="ADMIN")
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)
    admin_headers = {"Authorization": f"Bearer {create_access_token(admin_user)}"}
    admin_list_response = client.get("/api/v1/install-jobs", headers=admin_headers)
    assert admin_list_response.status_code == status.HTTP_200_OK
    admin_listed = admin_list_response.json()
    assert admin_listed
    for item in admin_listed:
        for key in ("pfx_base64", "password", "payload_token", "source_path"):
            assert key not in item
