from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("certhub.econtrole_webhook")

_TIMEOUT_SECONDS = 10.0


def _is_configured() -> bool:
    return bool(
        settings.econtrole_webhook_url
        and settings.econtrole_webhook_token
        and settings.econtrole_webhook_org_slug
    )


def _build_headers(org_slug: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.econtrole_webhook_token}",
        "Content-Type": "application/json",
        "X-Org-Slug": org_slug,
    }


def _post(payload: dict[str, Any], org_slug: str) -> None:
    if not settings.econtrole_webhook_enabled:
        logger.debug("econtrole webhook disabled; skipping")
        return
    if not _is_configured():
        logger.error("econtrole webhook missing required configuration; skipping")
        return
    try:
        response = httpx.post(
            settings.econtrole_webhook_url,
            headers=_build_headers(org_slug),
            json=payload,
            timeout=_TIMEOUT_SECONDS,
            verify=settings.econtrole_webhook_verify_tls,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "econtrole webhook http error mode=%s status=%s body=%s",
            payload.get("mode"),
            exc.response.status_code,
            exc.response.text[:500],
        )
    except httpx.HTTPError as exc:
        logger.error("econtrole webhook network error mode=%s error=%s", payload.get("mode"), exc)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("econtrole webhook unexpected error mode=%s error=%s", payload.get("mode"), exc)


def notify_upsert(org_slug: str, certificates: list[dict]) -> None:
    """Envia mode=upsert com lista de certificados."""
    deduped: list[dict] = []
    seen_ids: set[str] = set()
    for certificate in certificates:
        cert_id = certificate.get("id")
        if isinstance(cert_id, str) and cert_id:
            if cert_id in seen_ids:
                continue
            seen_ids.add(cert_id)
        deduped.append(certificate)
    payload = {
        "mode": "upsert",
        "org_slug": org_slug,
        "certificates": deduped,
    }
    _post(payload, org_slug)


def notify_delete(org_slug: str, deleted_cert_ids: list[str]) -> None:
    """Envia mode=delete com lista de cert_ids removidos."""
    deduped_ids = list(dict.fromkeys(cert_id for cert_id in deleted_cert_ids if cert_id))
    payload = {
        "mode": "delete",
        "org_slug": org_slug,
        "deleted_cert_ids": deduped_ids,
    }
    _post(payload, org_slug)


def notify_full_sync(org_slug: str, certificates: list[dict]) -> None:
    """Envia mode=full com todos os certificados da org."""
    payload = {
        "mode": "full",
        "org_slug": org_slug,
        "certificates": certificates,
    }
    _post(payload, org_slug)
