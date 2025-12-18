import importlib.util
from pathlib import Path

from app.models import AuditLog, User

helpers_path = Path(__file__).resolve().parent / "helpers.py"
helpers_spec = importlib.util.spec_from_file_location("tests.helpers", helpers_path)
helpers = importlib.util.module_from_spec(helpers_spec)
assert helpers_spec and helpers_spec.loader
helpers_spec.loader.exec_module(helpers)

create_user = helpers.create_user
headers = helpers.headers


def test_dev_updates_role_and_auto_approve(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        dev = create_user(db, role="DEV")
        viewer = create_user(db, role="VIEW", auto_approve=False)

    response = client.patch(
        f"/api/v1/admin/users/{viewer.id}",
        json={
            "role_global": "ADMIN",
            "auto_approve_install_jobs": True,
            "is_active": False,
        },
        headers=headers(dev),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["role_global"] == "ADMIN"
    assert payload["auto_approve_install_jobs"] is True
    assert payload["is_active"] is False
    assert payload["updated_at"] is not None

    with SessionLocal() as db:
        audits = db.query(AuditLog).order_by(AuditLog.timestamp).all()
        assert audits[-1].action == "USER_UPDATED"
        assert audits[-1].meta_json == {
            "changes": {
                "auto_approve_install_jobs": [False, True],
                "role_global": ["VIEW", "ADMIN"],
                "is_active": [True, False],
            }
        }


def test_admin_updates_only_auto_approve(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        admin = create_user(db, role="ADMIN")
        viewer = create_user(db, role="VIEW", auto_approve=False)

    response = client.patch(
        f"/api/v1/admin/users/{viewer.id}",
        json={"auto_approve_install_jobs": True},
        headers=headers(admin),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["auto_approve_install_jobs"] is True
    assert payload["role_global"] == "VIEW"

    with SessionLocal() as db:
        audits = db.query(AuditLog).order_by(AuditLog.timestamp).all()
        assert audits[-1].meta_json == {
            "changes": {"auto_approve_install_jobs": [False, True]}
        }


def test_admin_cannot_change_role(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        admin = create_user(db, role="ADMIN")
        viewer = create_user(db, role="VIEW")

    response = client.patch(
        f"/api/v1/admin/users/{viewer.id}",
        json={"role_global": "DEV"},
        headers=headers(admin),
    )

    assert response.status_code == 403

    with SessionLocal() as db:
        refreshed = db.get(User, viewer.id)
        assert refreshed.role_global == "VIEW"


def test_view_cannot_update_users(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        viewer = create_user(db, role="VIEW")

    response = client.patch(
        f"/api/v1/admin/users/{viewer.id}",
        json={"auto_approve_install_jobs": True},
        headers=headers(viewer),
    )

    assert response.status_code == 403


def test_cannot_update_user_from_other_org(test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        dev = create_user(db, role="DEV", org_id=1)
        other_org_user = create_user(db, role="VIEW", org_id=2)

    response = client.patch(
        f"/api/v1/admin/users/{other_org_user.id}",
        json={"auto_approve_install_jobs": True},
        headers=headers(dev),
    )

    assert response.status_code == 404
