from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Certificate

DATE_FORMAT = "%b %d %H:%M:%S %Y %Z"
CERT_EXTENSIONS = {".pfx", ".p12"}
MAX_ERRORS = 10


class CertificateParserError(Exception):
    """Raised when OpenSSL cannot parse the certificate."""


@dataclass
class ParsedCertificate:
    path: Path
    name: str
    subject: str | None
    issuer: str | None
    serial_number: str | None
    not_before: datetime | None
    not_after: datetime | None
    sha1_fingerprint: str | None
    password_used: str | None
    parse_error: str | None


def _guess_password(path: Path) -> str | None:
    stem = path.stem
    match = re.search(r"senha[:\s_-]+(.+)", stem, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _parse_datetime(raw_value: str) -> datetime:
    return datetime.strptime(raw_value, DATE_FORMAT).replace(tzinfo=timezone.utc)


def _run_openssl_extract(path: Path, password: str) -> str:
    try:
        pkcs12_cmd = [
            str(settings.openssl_path),
            "pkcs12",
            "-in",
            str(path),
            "-passin",
            f"pass:{password}",
            "-nokeys",
            "-clcerts",
            "-nodes",
        ]
        pem_bytes = subprocess.check_output(pkcs12_cmd, stderr=subprocess.PIPE)
        x509_cmd = [
            str(settings.openssl_path),
            "x509",
            "-noout",
            "-subject",
            "-issuer",
            "-serial",
            "-dates",
            "-fingerprint",
            "-sha1",
        ]
        return subprocess.check_output(
            x509_cmd, input=pem_bytes, stderr=subprocess.PIPE
        ).decode("utf-8", errors="ignore")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="ignore").strip()
        raise CertificateParserError(stderr or "unable to parse certificate") from exc


def _extract_metadata(path: Path, candidates: Iterable[str]) -> tuple[ParsedCertificate, bool]:
    last_error: str | None = None
    for password in dict.fromkeys(candidates):
        try:
            raw_output = _run_openssl_extract(path, password)
            parsed = _parse_metadata_output(raw_output)
            return (
                ParsedCertificate(
                    path=path,
                    name=path.stem,
                    password_used=password or None,
                    parse_error=None,
                    **parsed,
                ),
                True,
            )
        except CertificateParserError as exc:
            last_error = str(exc)
            continue
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
            parse_error=last_error or "failed to parse certificate",
        ),
        False,
    )


def _parse_metadata_output(raw_output: str) -> dict[str, str | datetime | None]:
    subject = issuer = serial = fingerprint = None
    not_before = not_after = None
    for line in raw_output.splitlines():
        if line.startswith("subject="):
            subject = line.removeprefix("subject=").strip()
        elif line.startswith("issuer="):
            issuer = line.removeprefix("issuer=").strip()
        elif line.startswith("serial="):
            serial = line.removeprefix("serial=").strip()
        elif line.startswith("notBefore="):
            try:
                not_before = _parse_datetime(line.removeprefix("notBefore=").strip())
            except ValueError:
                not_before = None
        elif line.startswith("notAfter="):
            try:
                not_after = _parse_datetime(line.removeprefix("notAfter=").strip())
            except ValueError:
                not_after = None
        elif "Fingerprint=" in line:
            fingerprint = line.split("=", 1)[1].strip().replace(":", "").upper()
    return {
        "subject": subject,
        "issuer": issuer,
        "serial_number": serial,
        "not_before": not_before,
        "not_after": not_after,
        "sha1_fingerprint": fingerprint,
    }


def _candidate_passwords(path: Path) -> list[str]:
    guessed = _guess_password(path)
    candidates: list[str] = []
    if guessed is not None:
        candidates.append(guessed)
    candidates.append("")
    return candidates


def ingest_certificates_from_fs(
    db: Session, *, org_id: int, dry_run: bool = False, limit: int = 0
) -> dict[str, int | list[str]]:
    root_path = settings.certs_root_path.expanduser()
    if not root_path.exists() or not root_path.is_dir():
        raise FileNotFoundError(f"CERTS_ROOT_PATH not found: {root_path}")

    files = [
        path
        for path in sorted(root_path.iterdir())
        if path.is_file() and path.suffix.lower() in CERT_EXTENSIONS
    ]
    if limit and limit > 0:
        files = files[:limit]

    inserted = updated = failed = 0
    errors: list[str] = []

    for path in files:
        parsed, success = _extract_metadata(path, _candidate_passwords(path))
        if not success:
            failed += 1
            if len(errors) < MAX_ERRORS:
                errors.append(f"{path.name}: {parsed.parse_error}")

        existing = _find_existing_certificate(
            db, org_id=org_id, sha1=parsed.sha1_fingerprint, serial=parsed.serial_number, name=parsed.name
        )

        if dry_run:
            if existing:
                updated += 1
            else:
                inserted += 1
            continue

        if existing:
            _update_certificate(existing, parsed)
            updated += 1
        else:
            db.add(_build_certificate(org_id, parsed))
            inserted += 1

    if not dry_run:
        db.commit()

    total = len(files)
    return {"inserted": inserted, "updated": updated, "failed": failed, "total": total, "errors": errors}


def _find_existing_certificate(
    db: Session, *, org_id: int, sha1: str | None, serial: str | None, name: str
) -> Certificate | None:
    if sha1:
        existing = db.execute(
            select(Certificate).where(
                Certificate.org_id == org_id, Certificate.sha1_fingerprint == sha1
            )
        ).scalar_one_or_none()
        if existing:
            return existing
    if serial:
        existing = db.execute(
            select(Certificate).where(
                Certificate.org_id == org_id, Certificate.serial_number == serial
            )
        ).scalar_one_or_none()
        if existing:
            return existing
    return db.execute(
        select(Certificate).where(Certificate.org_id == org_id, Certificate.name == name)
    ).scalar_one_or_none()


def _update_certificate(target: Certificate, parsed: ParsedCertificate) -> None:
    target.subject = parsed.subject
    target.issuer = parsed.issuer
    target.serial_number = parsed.serial_number
    target.not_before = parsed.not_before
    target.not_after = parsed.not_after
    target.sha1_fingerprint = parsed.sha1_fingerprint
    target.parse_error = parsed.parse_error
    target.source_path = str(parsed.path)


def _build_certificate(org_id: int, parsed: ParsedCertificate) -> Certificate:
    return Certificate(
        org_id=org_id,
        name=parsed.name,
        subject=parsed.subject,
        issuer=parsed.issuer,
        serial_number=parsed.serial_number,
        not_before=parsed.not_before,
        not_after=parsed.not_after,
        sha1_fingerprint=parsed.sha1_fingerprint,
        parse_error=parsed.parse_error,
        source_path=str(parsed.path),
    )
