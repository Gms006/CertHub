from datetime import datetime, timezone

import importlib.util
from pathlib import Path

helpers_path = Path(__file__).resolve().parent / "helpers.py"
helpers_spec = importlib.util.spec_from_file_location("tests.helpers", helpers_path)
helpers = importlib.util.module_from_spec(helpers_spec)
assert helpers_spec and helpers_spec.loader
helpers_spec.loader.exec_module(helpers)

from app import models
from app.services import certificate_ingest
from app.services.certificate_ingest import ParsedCertificate

create_certificate = helpers.create_certificate
create_user = helpers.create_user
headers = helpers.headers


def test_ingest_counts_and_preserves_valid_data(monkeypatch, tmp_path, test_client_and_session):
    client, SessionLocal = test_client_and_session
    with SessionLocal() as db:
        dev = create_user(db, role="DEV")
        existing_ok = create_certificate(
            db,
            name="existing-ok",
            subject="Old Subject",
            issuer="Old Issuer",
            sha1_fingerprint="SHA-OK",
        )
        existing_fail = create_certificate(
            db,
            name="existing-fail",
            subject="Keep Subject",
            issuer="Keep Issuer",
            sha1_fingerprint="SHA-FAIL",
        )

    for filename in ["existing-fail.pfx", "existing-ok.pfx", "new-cert.pfx"]:
        (tmp_path / filename).write_text("dummy")

    def fake_extract_metadata(path, _):
        if path.name == "existing-ok.pfx":
            return (
                ParsedCertificate(
                    path=path,
                    name=path.stem,
                    subject="Updated Subject",
                    issuer="New Issuer",
                    serial_number="SER-OK",
                    not_before=datetime(2024, 1, 1, tzinfo=timezone.utc),
                    not_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    sha1_fingerprint="SHA-OK",
                    password_used=None,
                    parse_error=None,
                ),
                True,
            )
        if path.name == "new-cert.pfx":
            return (
                ParsedCertificate(
                    path=path,
                    name=path.stem,
                    subject="New Subject",
                    issuer="Issuer X",
                    serial_number="SER-NEW",
                    not_before=datetime(2024, 2, 1, tzinfo=timezone.utc),
                    not_after=datetime(2026, 2, 1, tzinfo=timezone.utc),
                    sha1_fingerprint="SHA-NEW",
                    password_used=None,
                    parse_error=None,
                ),
                True,
            )
        return (
            ParsedCertificate(
                path=path,
                name=path.stem,
                subject=None,
                issuer=None,
                serial_number=None,
                not_before=None,
                not_after=None,
                sha1_fingerprint=None,
                password_used=None,
                parse_error="failed to parse",
            ),
            False,
        )

    monkeypatch.setattr(certificate_ingest.settings, "certs_root_path", tmp_path)
    monkeypatch.setattr(certificate_ingest, "_extract_metadata", fake_extract_metadata)

    response = client.post(
        "/api/v1/admin/certificates/ingest-from-fs",
        json={"dry_run": False},
        headers=headers(dev),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "inserted": 1,
        "updated": 1,
        "failed": 1,
        "total": 3,
        "pruned": 0,
        "deduped": 0,
        "errors": [
            {"filename": "existing-fail.pfx", "reason": "failed to parse", "exception": None}
        ],
    }

    with SessionLocal() as db:
        updated_cert = db.get(models.Certificate, existing_ok.id)
        failed_cert = db.get(models.Certificate, existing_fail.id)
        new_cert = db.query(models.Certificate).filter_by(name="new-cert").one()

        assert updated_cert.subject == "Updated Subject"
        assert updated_cert.parse_ok is True
        assert updated_cert.parse_error is None
        assert updated_cert.last_ingested_at is not None

        assert failed_cert.subject == "Keep Subject"
        assert failed_cert.parse_ok is False
        assert failed_cert.parse_error == "failed to parse"
        assert failed_cert.last_error_at is not None
        assert failed_cert.last_ingested_at is not None

        assert new_cert.subject == "New Subject"
        assert new_cert.parse_ok is True
        assert new_cert.last_ingested_at is not None


def test_guess_password_variations():
    cases = [
        ("cert senha 123.pfx", "123"),
        ("cert-senha:abc.pfx", "abc"),
        ("cert_senha-ABC123.pfx", "ABC123"),
        ("cert senha_789.pfx", "789"),
        ("cert-senha \"quoted\".pfx", "\"quoted\""),
    ]
    for filename, expected in cases:
        assert certificate_ingest._guess_password(Path(filename)) == expected
