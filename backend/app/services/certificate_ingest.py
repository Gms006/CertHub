from __future__ import annotations

import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Certificate
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates

DATE_FORMAT = "%b %d %H:%M:%S %Y %Z"
CERT_EXTENSIONS = {".pfx", ".p12"}
MAX_ERRORS = 50


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
    match = re.search(r"senha(?:\s*[:_-]?\s+|\s*[:_-]\s*)(\S+)$", stem, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _parse_datetime(raw_value: str) -> datetime:
    normalized = re.sub(r"\s+", " ", raw_value.strip())
    return datetime.strptime(normalized, DATE_FORMAT).replace(tzinfo=timezone.utc)


def _run_openssl_extract(path: Path, password: str, *, legacy: bool = False) -> str:
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
        if legacy:
            pkcs12_cmd.append("-legacy")
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
            parsed = parse_pkcs12(path, password)
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
        except Exception as exc:
            last_error = str(exc)
            continue
    for password in dict.fromkeys(candidates):
        try:
            raw_output = _run_openssl_extract(path, password)
        except CertificateParserError as exc:
            last_error = str(exc)
            try:
                raw_output = _run_openssl_extract(path, password, legacy=True)
            except CertificateParserError as legacy_exc:
                last_error = str(legacy_exc)
                continue
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
            serial = _normalize_serial(line.removeprefix("serial=").strip())
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
        candidates.extend(_password_variations(guessed))
    candidates.append("")
    return candidates


def _password_variations(password: str) -> list[str]:
    variations = [password, password.strip()]
    for quote in ('"', "'"):
        variations.append(password.strip().strip(quote))
    return [value for value in dict.fromkeys(variations) if value]


def dotnet_serial_from_int(serial_int: int) -> str:
    length = max(1, (serial_int.bit_length() + 7) // 8)
    raw_bytes = serial_int.to_bytes(length, byteorder="big")
    reversed_bytes = raw_bytes[::-1]
    return reversed_bytes.hex().upper()


def _normalize_serial(serial_value: str | None) -> str | None:
    if not serial_value:
        return None
    cleaned = serial_value.strip()
    if cleaned.lower().startswith("0x"):
        cleaned = cleaned[2:]
    try:
        serial_int = int(cleaned, 16)
        return dotnet_serial_from_int(serial_int)
    except ValueError:
        try:
            serial_int = int(cleaned)
            return dotnet_serial_from_int(serial_int)
        except ValueError:
            return None


def _certificate_datetime(cert_value: datetime) -> datetime:
    return cert_value.astimezone(timezone.utc) if cert_value.tzinfo else cert_value.replace(
        tzinfo=timezone.utc
    )


def parse_pkcs12(path: Path, password: str) -> dict[str, str | datetime | None]:
    raw_bytes = path.read_bytes()
    password_bytes = password.encode() if password else b""
    try:
        _key, cert, _additional = load_key_and_certificates(raw_bytes, password_bytes)
    except Exception as exc:
        if password == "":
            _key, cert, _additional = load_key_and_certificates(raw_bytes, None)
        else:
            raise exc
    if cert is None:
        raise CertificateParserError("certificate not found in PKCS12 bundle")
    subject = cert.subject.rfc4514_string()
    issuer = cert.issuer.rfc4514_string()
    serial_number = dotnet_serial_from_int(cert.serial_number)
    not_before = getattr(cert, "not_valid_before_utc", None)
    if not_before is None:
        not_before = _certificate_datetime(cert.not_valid_before)
    not_after = getattr(cert, "not_valid_after_utc", None)
    if not_after is None:
        not_after = _certificate_datetime(cert.not_valid_after)
    sha1_fingerprint = cert.fingerprint(hashes.SHA1()).hex().upper()
    return {
        "subject": subject,
        "issuer": issuer,
        "serial_number": serial_number,
        "not_before": not_before,
        "not_after": not_after,
        "sha1_fingerprint": sha1_fingerprint,
    }


def ingest_certificates_from_fs(
    db: Session,
    *,
    org_id: int,
    dry_run: bool = False,
    limit: int = 0,
    prune_missing: bool = False,
    dedupe: bool = False,
) -> dict[str, int | list[dict[str, str | None]]]:
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

    results: list[dict[str, str | uuid.UUID | None]] = []

    for path in files:
        parsed, success = _extract_metadata(path, _candidate_passwords(path))
        existing = _find_existing_certificate(
            db, org_id=org_id, sha1=parsed.sha1_fingerprint, serial=parsed.serial_number, name=parsed.name
        )

        if dry_run:
            results.append(
                {
                    "action": "updated" if existing else "inserted",
                    "cert_id": existing.id if existing else None,
                    "file": path.name,
                    "error": parsed.parse_error if not success else None,
                }
            )
            if not success:
                results[-1]["action"] = "failed"
            continue

        if success:
            if existing:
                _update_certificate(existing, parsed)
                action = "updated"
                cert_id = existing.id
            else:
                certificate = _build_certificate(org_id, parsed)
                db.add(certificate)
                action = "inserted"
                cert_id = certificate.id
        else:
            action = "failed"
            cert_id = existing.id if existing else None
            if existing:
                _mark_parse_failure(existing, parsed)

        results.append(
            {
                "action": action,
                "cert_id": cert_id,
                "file": path.name,
                "error": parsed.parse_error if not success else None,
            }
        )

    pruned = 0
    deduped = 0

    if not dry_run:
        if prune_missing:
            pruned = _prune_missing_certificates(db, org_id=org_id)
        if dedupe:
            deduped = _dedupe_certificates(db, org_id=org_id)
        db.commit()

    total = len(files)
    inserted = sum(1 for item in results if item["action"] == "inserted")
    updated = sum(1 for item in results if item["action"] == "updated")
    failed = sum(1 for item in results if item["action"] == "failed")
    errors = [
        {"filename": item["file"], "reason": item["error"], "exception": None}
        for item in results
        if item["action"] == "failed" and item.get("error")
    ][:MAX_ERRORS]

    return {
        "inserted": inserted,
        "updated": updated,
        "failed": failed,
        "total": total,
        "pruned": pruned,
        "deduped": deduped,
        "errors": errors,
    }


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
    target.parse_ok = True
    target.parse_error = None
    target.source_path = str(parsed.path)
    target.last_ingested_at = datetime.now(timezone.utc)
    target.last_error_at = None


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
        parse_ok=True,
        parse_error=None,
        source_path=str(parsed.path),
        last_ingested_at=datetime.now(timezone.utc),
        last_error_at=None,
    )


def _mark_parse_failure(target: Certificate, parsed: ParsedCertificate) -> None:
    now = datetime.now(timezone.utc)
    target.parse_ok = False
    target.parse_error = parsed.parse_error
    target.last_ingested_at = now
    target.last_error_at = now
    if target.source_path is None:
        target.source_path = str(parsed.path)


def _prune_missing_certificates(db: Session, *, org_id: int) -> int:
    certificates = db.execute(
        select(Certificate).where(
            Certificate.org_id == org_id, Certificate.source_path.is_not(None)
        )
    ).scalars()
    removed = 0
    for certificate in certificates:
        if certificate.source_path and not Path(certificate.source_path).exists():
            db.delete(certificate)
            removed += 1
    return removed


def _dedupe_certificates(db: Session, *, org_id: int) -> int:
    certificates = db.execute(
        select(Certificate).where(Certificate.org_id == org_id)
    ).scalars()
    by_sha1: dict[str, list[Certificate]] = {}
    by_serial: dict[str, list[Certificate]] = {}
    for certificate in certificates:
        if certificate.sha1_fingerprint:
            by_sha1.setdefault(certificate.sha1_fingerprint, []).append(certificate)
        elif certificate.serial_number:
            by_serial.setdefault(certificate.serial_number, []).append(certificate)

    removed_ids: set[uuid.UUID] = set()

    def remove_duplicates(groups: dict[str, list[Certificate]]) -> None:
        for group in groups.values():
            if len(group) <= 1:
                continue
            group_sorted = sorted(
                group,
                key=lambda cert: cert.last_ingested_at
                or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            for duplicate in group_sorted[1:]:
                if duplicate.id in removed_ids:
                    continue
                removed_ids.add(duplicate.id)
                db.delete(duplicate)

    remove_duplicates(by_sha1)
    remove_duplicates(by_serial)
    return len(removed_ids)
