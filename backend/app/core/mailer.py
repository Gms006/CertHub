from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def _reset_link(token: str) -> str | None:
    if not settings.frontend_base_url:
        return None
    base = settings.frontend_base_url.rstrip("/")
    return f"{base}/reset-password?token={token}"


def send_reset_password_email(*, recipient: str, token: str) -> None:
    reset_link = _reset_link(token)
    if not reset_link:
        logger.warning("FRONTEND_BASE_URL not configured; skipping reset password email.")
        return

    if not settings.smtp_host or not settings.smtp_from:
        if settings.env.lower() == "dev":
            logger.info("Reset password link for %s: %s", recipient, reset_link)
        else:
            logger.warning("SMTP not configured; skipping reset password email.")
        return

    message = EmailMessage()
    message["Subject"] = "Redefinição de senha - CertHub"
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message.set_content(
        "\n".join(
            [
                "Olá,",
                "",
                "Recebemos uma solicitação para redefinir sua senha no CertHub.",
                "Se foi você, clique no link abaixo para criar uma nova senha:",
                "",
                reset_link,
                "",
                "Se você não solicitou a redefinição, pode ignorar este e-mail.",
            ]
        )
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.ehlo()
            if settings.smtp_user and settings.smtp_pass:
                smtp.starttls()
                smtp.login(settings.smtp_user, settings.smtp_pass)
            smtp.send_message(message)
    except smtplib.SMTPException:
        logger.exception("Failed to send reset password email.")
