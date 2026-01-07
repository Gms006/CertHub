from datetime import datetime, timedelta, timezone

import importlib.util
from pathlib import Path

helpers_path = Path(__file__).resolve().parent / "helpers.py"
helpers_spec = importlib.util.spec_from_file_location("tests.helpers", helpers_path)
helpers = importlib.util.module_from_spec(helpers_spec)
assert helpers_spec and helpers_spec.loader
helpers_spec.loader.exec_module(helpers)

create_certificate = helpers.create_certificate
create_device = helpers.create_device
create_user = helpers.create_user
headers = helpers.headers


def test_keep_until_blocked_when_device_disallows(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        admin = create_user(db, role="ADMIN")
        device = create_device(db, allow_keep_until=False)
        cert = create_certificate(db)

    keep_until = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={"device_id": str(device.id), "cleanup_mode": "KEEP_UNTIL", "keep_until": keep_until},
        headers=headers(admin),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "cleanup_mode KEEP_UNTIL not allowed for device"


def test_exempt_blocked_when_device_disallows(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        admin = create_user(db, role="ADMIN")
        device = create_device(db, allow_exempt=False)
        cert = create_certificate(db)

    response = client.post(
        f"/api/v1/certificados/{cert.id}/install",
        json={
            "device_id": str(device.id),
            "cleanup_mode": "EXEMPT",
            "keep_reason": "testing",
        },
        headers=headers(admin),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "cleanup_mode EXEMPT not allowed for device"
