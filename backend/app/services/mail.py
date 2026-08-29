"""Local email via MailHog SMTP (fully local, no external delivery)."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.logging import log

SMTP_HOST = "mailhog"
SMTP_PORT = 1025
FROM = "no-reply@returnguard.local"


def send(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.send_message(msg)
        log.info("mail.sent", to=to, subject=subject)
    except OSError as e:
        # MailHog being down must not break the user flow; it's a local catcher.
        log.warning("mail.failed", to=to, subject=subject, error=str(e))
