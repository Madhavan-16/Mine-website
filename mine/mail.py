"""Outbound SMTP email (optional). Configure via MAIL_* environment variables."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)


def _looks_placeholder(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return "replace_with_" in t or "example.com" in t


def normalize_email(addr: str) -> str | None:
    """Return canonical lower-case address for policy matching, or None if invalid."""
    from email_validator import EmailNotValidError, validate_email

    raw = (addr or "").strip()
    if not raw:
        return None
    try:
        v = validate_email(raw, check_deliverability=False)
        return v.normalized.lower()
    except EmailNotValidError:
        return None


def mail_ready(app: Flask) -> bool:
    """True when outbound mail is enabled and minimally configured."""
    if not app.config.get("MAIL_ENABLED"):
        return False
    if not (app.config.get("MAIL_DEFAULT_SENDER") or "").strip():
        return False
    if app.config.get("MAIL_DUMMY"):
        return True
    if not (app.config.get("MAIL_SERVER") or "").strip():
        return False
    return True


def permitted_recipient_emails(app: Flask, db) -> set[str]:
    """Emails the app may send to: active users plus optional MAIL_EXTRA_ALLOWLIST (normalized)."""
    rows = db.execute(
        """
        SELECT trim(email) AS e
        FROM users
        WHERE is_active = 1 AND email IS NOT NULL AND trim(email) != ''
        """
    ).fetchall()
    out: set[str] = set()
    for r in rows:
        raw = (r["e"] or "").strip()
        n = normalize_email(raw)
        if n:
            out.add(n)
    for extra in app.config.get("MAIL_EXTRA_ALLOWLIST") or frozenset():
        n = normalize_email(extra)
        if n:
            out.add(n)
    return out


def send_email(
    app: Flask,
    to_addrs: list[str],
    subject: str,
    text_body: str,
    *,
    sender_override: str | None = None,
    smtp_username_override: str | None = None,
    smtp_password_override: str | None = None,
) -> tuple[bool, str | None]:
    """
    Send one plain-text message to all addresses in to_addrs (To header lists them).

    Returns (success, error_message).
    """
    if not mail_ready(app):
        return (
            False,
            "Mail is not configured. Set MAIL_ENABLED=1 and MAIL_DEFAULT_SENDER. "
            "For local testing without SMTP, add MAIL_DUMMY=1; for production add MAIL_SERVER (and usually TLS/auth).",
        )

    recipients = [a.strip() for a in to_addrs if a and a.strip()]
    if not recipients:
        return False, "No recipients."

    cfg = app.config
    sender = (sender_override or cfg.get("MAIL_DEFAULT_SENDER") or "").strip()

    if cfg.get("MAIL_DUMMY"):
        raw_path = (cfg.get("MAIL_DUMMY_PATH") or "").strip()
        path = Path(raw_path) if raw_path else Path(cfg["BASE_DIR"]) / "logs" / "mail-outbox.log"
        if not path.is_absolute():
            path = Path(cfg["BASE_DIR"]) / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).isoformat()
            block = (
                f"\n{'=' * 72}\n"
                f"Time (UTC): {ts}\n"
                f"From: {sender}\n"
                f"To: {', '.join(recipients)}\n"
                f"Subject: {subject}\n"
                f"{'-' * 72}\n"
                f"{text_body}\n"
            )
            with path.open("a", encoding="utf-8") as fh:
                fh.write(block)
        except OSError as e:
            logger.warning("MAIL_DUMMY write failed: %s", e)
            return False, f"Could not write dev mailbox file: {e}"
        logger.info("MAIL_DUMMY: recorded message for %s recipient(s) -> %s", len(recipients), path)
        return True, None

    host = (cfg.get("MAIL_SERVER") or "").strip()
    port = int(cfg.get("MAIL_PORT") or 587)
    timeout = int(cfg.get("MAIL_SMTP_TIMEOUT") or 30)
    use_ssl = bool(cfg.get("MAIL_USE_SSL"))
    use_tls = bool(cfg.get("MAIL_USE_TLS"))
    user = (smtp_username_override or cfg.get("MAIL_USERNAME") or "").strip()
    password = smtp_password_override if smtp_password_override is not None else (cfg.get("MAIL_PASSWORD") or "")

    if _looks_placeholder(sender) or _looks_placeholder(user) or _looks_placeholder(password):
        return (
            False,
            "SMTP is using placeholder values. Replace MAIL_USERNAME, MAIL_PASSWORD, and MAIL_DEFAULT_SENDER in .env with real mailbox credentials.",
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(text_body)

    try:
        refused: dict | None = None
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=timeout) as smtp:
                if cfg.get("MAIL_SMTP_DEBUG"):
                    smtp.set_debuglevel(1)
                if user:
                    smtp.login(user, password)
                refused = smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                if cfg.get("MAIL_SMTP_DEBUG"):
                    smtp.set_debuglevel(1)
                smtp.ehlo()
                if use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                if user:
                    smtp.login(user, password)
                refused = smtp.send_message(msg)
        if refused:
            logger.warning("SMTP refused recipients: %s", refused)
            keys = ", ".join(str(k) for k in refused.keys())
            return False, f"The mail server did not accept this message for: {keys}"
    except Exception as e:
        logger.warning("SMTP send failed: %s", e)
        return False, str(e) or "SMTP error"

    logger.info("SMTP send accepted for %s recipient(s): subject=%r", len(recipients), subject[:80])
    return True, None


def notify_moderators_by_email(app: Flask, subject: str, text_body: str) -> None:
    """If enabled, email all active admins/moderators who have an email address."""
    if not mail_ready(app) or not app.config.get("MAIL_NOTIFY_ON_PENDING"):
        return
    from mine.db import get_db

    db = get_db()
    rows = db.execute(
        """
        SELECT trim(email) AS e
        FROM users
        WHERE is_active = 1
          AND role IN ('admin', 'moderator')
          AND email IS NOT NULL
          AND trim(email) != ''
        """
    ).fetchall()
    addrs_set: set[str] = set()
    for r in rows:
        n = normalize_email((r["e"] or "").strip())
        if n:
            addrs_set.add(n)
    addrs = sorted(addrs_set)
    if not addrs:
        logger.info("MAIL_NOTIFY_ON_PENDING set but no moderator emails in database.")
        return
    ok, err = send_email(app, addrs, subject, text_body)
    if not ok:
        logger.warning("Could not email moderators: %s", err)
