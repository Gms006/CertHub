from __future__ import annotations

from pathlib import Path

import uuid

from sqlalchemy.sql.selectable import Select

from app import models
from app.services import econtrole_webhook
from app.workers import jobs_certificates
from tests import helpers


def _normalized(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def test_delete_certificate_by_path_removes_row(monkeypatch, tmp_path, test_client_and_session):
    _, SessionLocal = test_client_and_session
    path = tmp_path / "alpha.pfx"
    normalized_path = _normalized(path)

    with SessionLocal() as db:
        cert = helpers.create_certificate(
            db,
            name=path.stem,
            source_path=normalized_path,
        )

    monkeypatch.setattr(jobs_certificates, "SessionLocal", SessionLocal)

    result = jobs_certificates.delete_certificate_by_path(org_id=1, path=str(path))

    assert result["action"] == "deleted"
    assert result["strategy"] == "by_path"

    with SessionLocal() as db:
        assert db.get(models.Certificate, cert.id) is None


def test_delete_certificate_fallback_by_name(monkeypatch, tmp_path, test_client_and_session):
    _, SessionLocal = test_client_and_session
    path = tmp_path / "beta.pfx"
    normalized_path = _normalized(path)

    with SessionLocal() as db:
        cert = helpers.create_certificate(
            db,
            name=path.stem,
            source_path=f"{normalized_path}.old",
        )

    monkeypatch.setattr(jobs_certificates, "SessionLocal", SessionLocal)

    result = jobs_certificates.delete_certificate_by_path(org_id=1, path=str(path))

    assert result["action"] == "deleted"
    assert result["strategy"] == "by_name"

    with SessionLocal() as db:
        assert db.get(models.Certificate, cert.id) is None


def test_delete_certificate_ambiguous_does_not_delete(monkeypatch):
    class FakeResult:
        def __init__(self, *, rows=None):
            self._rows = rows or []

        def scalars(self):
            return self

        def all(self):
            return self._rows

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement):
            assert isinstance(statement, Select)
            return FakeResult(rows=[])

        def delete(self, _obj):
            raise AssertionError("delete should not be called for ambiguous result")

        def commit(self):
            raise AssertionError("commit should not be called for ambiguous result")

    class FakeSessionAmbiguous(FakeSession):
        def execute(self, statement):
            sql = str(statement)
            if "source_path" in sql:
                return FakeResult(rows=[])
            cert_a = models.Certificate(id=uuid.uuid4(), org_id=1, name="ambiguous")
            cert_b = models.Certificate(id=uuid.uuid4(), org_id=1, name="ambiguous")
            return FakeResult(rows=[cert_a, cert_b])

    monkeypatch.setattr(jobs_certificates, "SessionLocal", lambda: FakeSessionAmbiguous())

    result = jobs_certificates.delete_certificate_by_path(
        org_id=1, path=str(Path("/tmp/ambiguous.pfx"))
    )

    assert result["action"] == "ambiguous"
    assert result["strategy"] == "by_name"


def test_delete_certificate_webhook_failure_does_not_break_flow(
    monkeypatch, tmp_path, test_client_and_session
):
    _, SessionLocal = test_client_and_session
    path = tmp_path / "gamma.pfx"
    normalized_path = _normalized(path)

    with SessionLocal() as db:
        cert = helpers.create_certificate(db, name=path.stem, source_path=normalized_path)

    monkeypatch.setattr(jobs_certificates, "SessionLocal", SessionLocal)
    monkeypatch.setattr(econtrole_webhook.settings, "econtrole_webhook_enabled", True)
    monkeypatch.setattr(econtrole_webhook.settings, "econtrole_webhook_url", "http://localhost/webhook")
    monkeypatch.setattr(econtrole_webhook.settings, "econtrole_webhook_token", "token")

    def fake_post(*args, **kwargs):
        raise RuntimeError("network error")

    monkeypatch.setattr(econtrole_webhook.httpx, "post", fake_post)

    result = jobs_certificates.delete_certificate_by_path(org_id=1, path=str(path))

    assert result["action"] == "deleted"
    with SessionLocal() as db:
        assert db.get(models.Certificate, cert.id) is None


def test_delete_certificate_publishes_deleted_ids_payload(
    monkeypatch, tmp_path, test_client_and_session
):
    _, SessionLocal = test_client_and_session
    path = tmp_path / "delta.pfx"
    normalized_path = _normalized(path)

    with SessionLocal() as db:
        helpers.create_certificate(
            db,
            name=path.stem,
            source_path=normalized_path,
            serial_number="SER-DELTA",
            sha1_fingerprint="SHA-DELTA",
        )

    sent: list[dict] = []

    def fake_publish_deleted_ids(*, org_id, deleted_cert_ids):
        sent.append({"org_id": org_id, "deleted_cert_ids": deleted_cert_ids})
        return None

    monkeypatch.setattr(jobs_certificates, "SessionLocal", SessionLocal)
    monkeypatch.setattr(econtrole_webhook, "publish_deleted_ids", fake_publish_deleted_ids)

    result = jobs_certificates.delete_certificate_by_path(org_id=1, path=str(path))

    assert result["action"] == "deleted"
    assert len(sent) == 1
    assert sent[0]["org_id"] == 1
    assert len(sent[0]["deleted_cert_ids"]) == 1
    assert isinstance(sent[0]["deleted_cert_ids"][0], str)
