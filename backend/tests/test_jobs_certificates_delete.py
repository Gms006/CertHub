from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.sql.dml import Delete
from sqlalchemy.sql.selectable import Select

from app import models
from app.workers import jobs_certificates
from tests import helpers


class FakeResult:
    def __init__(self, *, rowcount: int | None = None, scalars: list[uuid.UUID] | None = None):
        self.rowcount = rowcount
        self._scalars = scalars or []

    def scalars(self):
        return self

    def all(self):
        return self._scalars


class FakeSession:
    def __init__(self):
        self.delete_calls = 0
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement):
        if isinstance(statement, Delete):
            self.delete_calls += 1
            return FakeResult(rowcount=0)
        if isinstance(statement, Select):
            return FakeResult(scalars=[uuid.uuid4(), uuid.uuid4()])
        raise AssertionError("Unexpected statement type")

    def commit(self):
        self.commits += 1


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
    fake_session = FakeSession()

    monkeypatch.setattr(jobs_certificates, "SessionLocal", lambda: fake_session)

    result = jobs_certificates.delete_certificate_by_path(
        org_id=1, path=str(Path("/tmp/ambiguous.pfx"))
    )

    assert result["action"] == "ambiguous"
    assert result["strategy"] == "by_name"
    assert fake_session.delete_calls == 1
    assert fake_session.commits == 0
