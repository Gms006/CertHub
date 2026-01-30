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
        subject="CN=Empresa 12345678000199, O=ACME LTDA, C=BR",
        issuer="CN=Autoridade Certificadora Teste, O=ACME, C=BR",
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

    certs_response = client.get("/api/v1/certificados", headers=headers)
    assert certs_response.status_code == status.HTTP_200_OK
    certs_payload = certs_response.json()
    assert certs_payload
    for item in certs_payload:
        assert "source_path" not in item
        assert "subject" not in item
        assert "issuer" not in item
        assert "org_id" not in item
        assert item["cn"] == "Empresa 12345678000199"
        assert item["issuer_cn"] == "Autoridade Certificadora Teste"
        assert item["document_type"] == "CNPJ"
        assert item["document_masked"] == "CNPJ 12********0199"

    cert_response = client.get(f"/api/v1/certificados/{certificate.id}", headers=headers)
    assert cert_response.status_code == status.HTTP_200_OK
    cert_payload = cert_response.json()
    assert "source_path" not in cert_payload
    assert "subject" not in cert_payload
    assert "issuer" not in cert_payload
    assert "org_id" not in cert_payload
    assert cert_payload["cn"] == "Empresa 12345678000199"
    assert cert_payload["issuer_cn"] == "Autoridade Certificadora Teste"
    assert cert_payload["document_type"] == "CNPJ"
    assert cert_payload["document_masked"] == "CNPJ 12********0199"

    technical_forbidden = client.get(
        f"/api/v1/certificados/{certificate.id}/technical",
        headers=headers,
    )
    assert technical_forbidden.status_code == status.HTTP_403_FORBIDDEN

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
    technical_response = client.get(
        f"/api/v1/certificados/{certificate.id}/technical",
        headers=admin_headers,
    )
    assert technical_response.status_code == status.HTTP_200_OK
    technical_payload = technical_response.json()
    assert technical_payload["subject"] == "CN=Empresa 12345678000199, O=ACME LTDA, C=BR"
    assert technical_payload["issuer"] == "CN=Autoridade Certificadora Teste, O=ACME, C=BR"
    assert "org_id" not in technical_payload
    assert "source_path" not in technical_payload

    admin_list_response = client.get("/api/v1/install-jobs", headers=admin_headers)
    assert admin_list_response.status_code == status.HTTP_200_OK
    admin_listed = admin_list_response.json()
    assert admin_listed
    for item in admin_listed:
        for key in ("pfx_base64", "password", "payload_token", "source_path"):
            assert key not in item
