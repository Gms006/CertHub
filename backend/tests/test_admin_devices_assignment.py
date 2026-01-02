import importlib.util
from pathlib import Path

helpers_path = Path(__file__).resolve().parent / "helpers.py"
helpers_spec = importlib.util.spec_from_file_location("tests.helpers", helpers_path)
helpers = importlib.util.module_from_spec(helpers_spec)
assert helpers_spec and helpers_spec.loader
helpers_spec.loader.exec_module(helpers)

create_user = helpers.create_user
create_device = helpers.create_device
headers = helpers.headers


def test_admin_assigns_and_clears_device_user(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        admin = create_user(db, role="ADMIN")
        assigned_user = create_user(db, role="VIEW", org_id=admin.org_id)

    response = client.post(
        "/api/v1/admin/devices",
        json={
            "hostname": "device-assigned-01",
            "assigned_user_id": str(assigned_user.id),
        },
        headers=headers(admin),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["assigned_user_id"] == str(assigned_user.id)

    response = client.patch(
        f"/api/v1/admin/devices/{payload['id']}",
        json={"assigned_user_id": None},
        headers=headers(admin),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assigned_user_id"] is None


def test_dev_can_toggle_device_auto_approve(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        dev = create_user(db, role="DEV")
        device = create_device(db)

    response = client.patch(
        f"/api/v1/admin/devices/{device.id}",
        json={"auto_approve": True},
        headers=headers(dev),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["auto_approve"] is True


def test_admin_cannot_toggle_device_auto_approve(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        admin = create_user(db, role="ADMIN")
        device = create_device(db)

    response = client.patch(
        f"/api/v1/admin/devices/{device.id}",
        json={"auto_approve": True},
        headers=headers(admin),
    )

    assert response.status_code == 403


def test_list_devices_returns_auto_approve_and_patch_updates(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        dev = create_user(db, role="DEV")
        device = create_device(db, auto_approve=False)

    list_response = client.get("/api/v1/admin/devices", headers=headers(dev))
    assert list_response.status_code == 200
    payload = list_response.json()
    listed = next(item for item in payload if item["id"] == str(device.id))
    assert listed["auto_approve"] is False

    patch_response = client.patch(
        f"/api/v1/admin/devices/{device.id}",
        json={"auto_approve": True},
        headers=headers(dev),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["auto_approve"] is True

    list_response = client.get("/api/v1/admin/devices", headers=headers(dev))
    payload = list_response.json()
    listed = next(item for item in payload if item["id"] == str(device.id))
    assert listed["auto_approve"] is True
