from __future__ import annotations

import re
from typing import Any, Literal

from app.models import Certificate
from app.schemas.certificate import CertificatePortalRead

CN_PATTERN = re.compile(r"(?:^|,)\s*CN=([^,]+)", flags=re.IGNORECASE)
CNPJ_PATTERN = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
CPF_PATTERN = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")


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
    for doc_type, pattern in (("CNPJ", CNPJ_PATTERN), ("CPF", CPF_PATTERN)):
        match = pattern.search(value)
        if match:
            digits = re.sub(r"\D", "", match.group(0))
            if len(digits) == 14 and doc_type == "CNPJ":
                return doc_type, digits
            if len(digits) == 11 and doc_type == "CPF":
                return doc_type, digits
    digits = re.sub(r"\D", "", value)
    if len(digits) == 14:
        return "CNPJ", digits
    if len(digits) == 11:
        return "CPF", digits
    if len(digits) >= 14:
        return "CNPJ", digits[:14]
    if len(digits) >= 11:
        return "CPF", digits[:11]
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
    doc_type, digits = _detect_document(" ".join(filter(None, [subject, cn])))
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
