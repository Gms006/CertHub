from __future__ import annotations

import re
from typing import Any, Literal

from app.models import Certificate
from app.schemas.certificate import CertificatePortalRead

CN_PATTERN = re.compile(r"(?:^|,)\s*CN=([^,]+)", flags=re.IGNORECASE)
CNPJ_PATTERN = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
CPF_PATTERN = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
ELEVEN_DIGITS_PATTERN = re.compile(r"(?<!\d)(\d{11})(?!\d)")
FOURTEEN_DIGITS_PATTERN = re.compile(r"(?<!\d)(\d{14})(?!\d)")


def sanitize_certificate_name(value: str) -> str:
    sanitized = value
    patterns = [
        r"senha\s*[:=]?\s*[^\s]+",
        r"senha[_-]?[^\s]+",
        r"\bsenha\b",
    ]
    for pattern in patterns:
        sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"[_-]{2,}", "-", sanitized)
    sanitized = re.sub(r"\s{2,}", " ", sanitized)
    sanitized = re.sub(r"[-_ ]+$", "", sanitized)
    sanitized = re.sub(r"^[-_ ]+", "", sanitized)
    return sanitized.strip()


def _extract_cn(value: str | None) -> str | None:
    if not value:
        return None
    match = CN_PATTERN.search(value)
    return match.group(1).strip() if match else None


def _detect_document(
    value: str | None,
) -> tuple[Literal["CNPJ", "CPF"] | None, str | None]:
    if not value:
        return None, None

    candidates: list[tuple[int, Literal["CNPJ", "CPF"], str]] = []

    for match in CNPJ_PATTERN.finditer(value):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) == 14:
            candidates.append((match.start(), "CNPJ", digits))
    for match in CPF_PATTERN.finditer(value):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) == 11:
            candidates.append((match.start(), "CPF", digits))

    for label, expected_len in (("CPF", 11), ("CNPJ", 14)):
        label_pattern = re.compile(rf"{label}\D{{0,10}}([\d./-]{{11,20}})", re.IGNORECASE)
        for match in label_pattern.finditer(value):
            digits = re.sub(r"\D", "", match.group(1))
            if len(digits) >= expected_len:
                doc_type: Literal["CNPJ", "CPF"] = "CPF" if label == "CPF" else "CNPJ"
                candidates.append((match.start(), doc_type, digits[:expected_len]))

    for match in FOURTEEN_DIGITS_PATTERN.finditer(value):
        candidates.append((match.start(), "CNPJ", match.group(1)))
    for match in ELEVEN_DIGITS_PATTERN.finditer(value):
        candidates.append((match.start(), "CPF", match.group(1)))

    if candidates:
        _position, doc_type, digits = min(candidates, key=lambda item: item[0])
        return doc_type, digits

    compact_digits = re.sub(r"\D", "", value)
    if len(compact_digits) == 14:
        return "CNPJ", compact_digits
    if len(compact_digits) == 11:
        return "CPF", compact_digits
    return None, None


def _mask_document(doc_type: str | None, digits: str | None) -> str | None:
    if not doc_type or not digits:
        return None
    if doc_type == "CNPJ" and len(digits) >= 14:
        return f"CNPJ {digits[:2]}{'*' * 8}{digits[10:14]}"
    if doc_type == "CPF" and len(digits) >= 11:
        return f"CPF ***.***.***-{digits[-2:]}"
    return None


def parse_subject_summary(subject: str | None, issuer: str | None) -> dict[str, str | None]:
    cn = _extract_cn(subject)
    issuer_cn = _extract_cn(issuer)
    doc_type, digits = _detect_document(" ".join(filter(None, [cn, subject])))
    return {
        "cn": cn,
        "issuer_cn": issuer_cn,
        "document_type": doc_type,
        "document_masked": _mask_document(doc_type, digits),
        "document_unmasked": digits,
    }


def certificate_to_portal_payload(certificate: Certificate) -> dict[str, Any]:
    summary = parse_subject_summary(certificate.subject, certificate.issuer)
    response = CertificatePortalRead.model_validate(certificate, from_attributes=True)
    response = response.model_copy(update={"name": sanitize_certificate_name(response.name), **summary})
    return response.model_dump(mode="json")
