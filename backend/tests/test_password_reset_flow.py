from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import hash_password, hash_token, verify_password
from app.models import AuditLog, AuthToken, User, UserSession
from tests.helpers import create_user


def test_password_reset_init_always_ok(test_client_and_session):
    client, session_factory = test_client_and_session

    with session_factory() as db:
        user = create_user(db)
        user.email = "user@example.com"
        user.password_hash = hash_password("Senha@123")
        db.commit()

    response_existing = client.post(
        "/api/v1/auth/password/reset/init", json={"email": "user@example.com"}
    )
    response_missing = client.post(
        "/api/v1/auth/password/reset/init", json={"email": "missing@example.com"}
    )

    assert response_existing.status_code == 200
    assert response_missing.status_code == 200
    assert (
        response_existing.json()["message"]
        == "Se existir conta com esse e-mail, enviaremos um link para resetar a senha."
    )

    with session_factory() as db:
        audit_actions = [
            entry.action
            for entry in db.execute(select(AuditLog.action).order_by(AuditLog.timestamp)).all()
        ]
        assert "PASSWORD_RESET_REQUESTED" in audit_actions


def test_password_reset_confirm_updates_password_and_audits(test_client_and_session):
    client, session_factory = test_client_and_session

    with session_factory() as db:
        user = create_user(db)
        user.email = "reset@example.com"
        user.password_hash = hash_password("Senha@123")
        session = UserSession(
            user_id=user.id,
            refresh_token_hash=hash_token("token"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(session)
        db.commit()

    init_response = client.post(
        "/api/v1/auth/password/reset/init", json={"email": "reset@example.com"}
    )
    token = init_response.json()["token"]

    confirm_response = client.post(
        "/api/v1/auth/password/reset/confirm",
        json={"token": token, "new_password": "NovaSenha@123"},
    )

    assert confirm_response.status_code == 200
    assert confirm_response.json()["message"] == "Senha atualizada com sucesso."

    with session_factory() as db:
        refreshed_user = db.execute(
            select(User).where(User.email == "reset@example.com")
        ).scalar_one()
        assert verify_password("NovaSenha@123", refreshed_user.password_hash)
        auth_token = db.execute(
            select(AuthToken).where(AuthToken.user_id == refreshed_user.id)
        ).scalar_one()
        assert auth_token.used_at is not None
        revoked_session = db.execute(
            select(UserSession).where(UserSession.user_id == refreshed_user.id)
        ).scalar_one()
        assert revoked_session.revoked_at is not None
        audit_actions = [
            entry.action
            for entry in db.execute(select(AuditLog.action).order_by(AuditLog.timestamp)).all()
        ]
        assert "PASSWORD_RESET" in audit_actions


def test_password_reset_confirm_rejects_invalid_tokens(test_client_and_session):
    client, session_factory = test_client_and_session

    with session_factory() as db:
        user = create_user(db)
        user.email = "expired@example.com"
        user.password_hash = hash_password("Senha@123")
        expired_token = AuthToken(
            user_id=user.id,
            token_hash=hash_token("expired"),
            purpose="RESET_PASSWORD",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        used_token = AuthToken(
            user_id=user.id,
            token_hash=hash_token("used"),
            purpose="RESET_PASSWORD",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            used_at=datetime.now(timezone.utc),
        )
        db.add_all([expired_token, used_token])
        db.commit()

    expired_response = client.post(
        "/api/v1/auth/password/reset/confirm",
        json={"token": "expired", "new_password": "NovaSenha@123"},
    )
    used_response = client.post(
        "/api/v1/auth/password/reset/confirm",
        json={"token": "used", "new_password": "NovaSenha@123"},
    )

    assert expired_response.status_code == 400
    assert used_response.status_code == 400
