from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Certificate
from app.services.certificate_projection import certificate_to_portal_payload

logger = logging.getLogger(__name__)


@dataclass
class WebhookPublishResult:
    attempted: bool
    success: bool
    mode: str
    sent: int
    status_code: int | None = None
    error: str | None = None


def _resolve_org_slug(org_id: int) -> str:
    raw_map = settings.econtrole_webhook_org_slug_map
    if raw_map:
        for pair in raw_map.split(","):
            key, sep, value = pair.partition(":")
            if not sep:
                continue
            if key.strip() == str(org_id):
                mapped = value.strip()
                if mapped:
                    return mapped
    if settings.econtrole_webhook_org_slug:
        return settings.econtrole_webhook_org_slug
    return str(org_id)


def _is_configured() -> bool:
    return bool(settings.econtrole_webhook_url and settings.econtrole_webhook_token)


def _headers_for(org_id: int) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.econtrole_webhook_token}",
        "X-Org-Slug": _resolve_org_slug(org_id),
    }


def _post(mode: str, *, org_id: int, certificates: list[dict[str, Any]]) -> WebhookPublishResult:
    if not settings.econtrole_webhook_enabled:
        return WebhookPublishResult(attempted=False, success=False, mode=mode, sent=0)
    if not _is_configured():
        logger.warning(
            "econtrole_webhook_skip reason=missing_config mode=%s org_id=%s",
            mode,
            org_id,
        )
        return WebhookPublishResult(
            attempted=False,
            success=False,
            mode=mode,
            sent=0,
            error="missing webhook url/token",
        )

    payload = {"certificates": certificates}
    try:
        response = httpx.post(
            settings.econtrole_webhook_url,
            params={"mode": mode},
            headers=_headers_for(org_id),
            json=payload,
            timeout=settings.econtrole_webhook_timeout_seconds,
            verify=settings.econtrole_webhook_verify_tls,
        )
        if 200 <= response.status_code < 300:
            logger.info(
                "econtrole_webhook_success mode=%s org_id=%s sent=%s status=%s",
                mode,
                org_id,
                len(certificates),
                response.status_code,
            )
            return WebhookPublishResult(
                attempted=True,
                success=True,
                mode=mode,
                sent=len(certificates),
                status_code=response.status_code,
            )
        logger.warning(
            "econtrole_webhook_failed mode=%s org_id=%s sent=%s status=%s body=%s",
            mode,
            org_id,
            len(certificates),
            response.status_code,
            response.text[:500],
        )
        return WebhookPublishResult(
            attempted=True,
            success=False,
            mode=mode,
            sent=len(certificates),
            status_code=response.status_code,
            error=f"http_{response.status_code}",
        )
    except Exception as exc:  # pragma: no cover - defensive catch for network/runtime errors
        logger.exception(
            "econtrole_webhook_exception mode=%s org_id=%s sent=%s error=%s",
            mode,
            org_id,
            len(certificates),
            exc,
        )
        return WebhookPublishResult(
            attempted=True,
            success=False,
            mode=mode,
            sent=len(certificates),
            error=str(exc),
        )


def _post_upsert_payload(
    *,
    org_id: int,
    payload: dict[str, Any],
    sent_count: int,
) -> WebhookPublishResult:
    if not settings.econtrole_webhook_enabled:
        return WebhookPublishResult(attempted=False, success=False, mode="upsert", sent=0)
    if not _is_configured():
        logger.warning(
            "econtrole_webhook_skip reason=missing_config mode=upsert org_id=%s",
            org_id,
        )
        return WebhookPublishResult(
            attempted=False,
            success=False,
            mode="upsert",
            sent=0,
            error="missing webhook url/token",
        )
    try:
        response = httpx.post(
            settings.econtrole_webhook_url,
            params={"mode": "upsert"},
            headers=_headers_for(org_id),
            json=payload,
            timeout=settings.econtrole_webhook_timeout_seconds,
            verify=settings.econtrole_webhook_verify_tls,
        )
        if 200 <= response.status_code < 300:
            logger.info(
                "econtrole_webhook_success mode=upsert org_id=%s sent=%s status=%s",
                org_id,
                sent_count,
                response.status_code,
            )
            return WebhookPublishResult(
                attempted=True,
                success=True,
                mode="upsert",
                sent=sent_count,
                status_code=response.status_code,
            )
        logger.warning(
            "econtrole_webhook_failed mode=upsert org_id=%s sent=%s status=%s body=%s",
            org_id,
            sent_count,
            response.status_code,
            response.text[:500],
        )
        return WebhookPublishResult(
            attempted=True,
            success=False,
            mode="upsert",
            sent=sent_count,
            status_code=response.status_code,
            error=f"http_{response.status_code}",
        )
    except Exception as exc:  # pragma: no cover
        logger.exception(
            "econtrole_webhook_exception mode=upsert org_id=%s sent=%s error=%s",
            org_id,
            sent_count,
            exc,
        )
        return WebhookPublishResult(
            attempted=True,
            success=False,
            mode="upsert",
            sent=sent_count,
            error=str(exc),
        )


def certificates_payload_from_ids(
    db: Session, *, org_id: int, certificate_ids: Iterable[Any]
) -> list[dict[str, Any]]:
    ids = [cert_id for cert_id in certificate_ids if cert_id is not None]
    if not ids:
        return []
    statement = (
        select(Certificate)
        .where(Certificate.org_id == org_id, Certificate.id.in_(ids))
        .order_by(Certificate.created_at)
    )
    certificates = db.execute(statement).scalars().all()
    return [certificate_to_portal_payload(certificate) for certificate in certificates]


def publish_upsert(
    *, org_id: int, certificates: list[dict[str, Any]]
) -> WebhookPublishResult:
    if not certificates:
        return WebhookPublishResult(attempted=False, success=False, mode="upsert", sent=0)
    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for certificate in certificates:
        cert_id = certificate.get("id")
        if isinstance(cert_id, str) and cert_id:
            if cert_id in seen_ids:
                continue
            seen_ids.add(cert_id)
        deduped.append(certificate)
    return _post_upsert_payload(
        org_id=org_id,
        payload={"certificates": deduped},
        sent_count=len(deduped),
    )


def publish_deleted_ids(*, org_id: int, deleted_cert_ids: list[str]) -> WebhookPublishResult:
    filtered_ids = [cert_id for cert_id in deleted_cert_ids if cert_id]
    if not filtered_ids:
        return WebhookPublishResult(attempted=False, success=False, mode="upsert", sent=0)
    deduped_ids = list(dict.fromkeys(filtered_ids))
    return _post_upsert_payload(
        org_id=org_id,
        payload={"deleted_cert_ids": deduped_ids},
        sent_count=len(deduped_ids),
    )


def publish_full_from_db(db: Session, *, org_id: int) -> WebhookPublishResult:
    statement = (
        select(Certificate)
        .where(Certificate.org_id == org_id)
        .order_by(Certificate.created_at)
    )
    certificates = db.execute(statement).scalars().all()
    payload = [certificate_to_portal_payload(certificate) for certificate in certificates]
    return _post("full", org_id=org_id, certificates=payload)
