from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _fernet_classes():
    try:
        mod = importlib.import_module("cryptography.fernet")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Token encryption dependency is missing (cryptography). Install requirements in the Python environment running MiNe."
        ) from exc
    return mod.Fernet, mod.InvalidToken


def _fernet_key(app) -> bytes:
    key = (app.config.get("MS_TOKEN_ENCRYPTION_KEY") or "").strip()
    if not key:
        raise RuntimeError("MS_TOKEN_ENCRYPTION_KEY is required for Outlook token encryption.")
    return key.encode("utf-8")


def _fernet(app):
    Fernet, _ = _fernet_classes()
    return Fernet(_fernet_key(app))


def _encrypt(app, text: str) -> str:
    return _fernet(app).encrypt(text.encode("utf-8")).decode("utf-8")


def _decrypt(app, text: str) -> str:
    _, InvalidToken = _fernet_classes()
    try:
        out = _fernet(app).decrypt((text or "").encode("utf-8"))
    except InvalidToken as exc:
        raise RuntimeError("Stored Outlook token is unreadable (encryption key mismatch).") from exc
    return out.decode("utf-8")


def load_user_token(db, app, user_id: int, provider: str = "microsoft_graph") -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT *
        FROM user_mail_tokens
        WHERE user_id = ? AND provider = ?
        """,
        (user_id, provider),
    ).fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "provider": row["provider"],
        "access_token": _decrypt(app, row["access_token_enc"]),
        "refresh_token": _decrypt(app, row["refresh_token_enc"]),
        "expires_at_utc": _parse_utc(row["expires_at_utc"]),
        "scope": row["scope"] or "",
        "tenant_hint": row["tenant_hint"] or "",
        "account_email": row["account_email"] or "",
        "account_display_name": row["account_display_name"] or "",
    }


def store_user_token(
    db,
    app,
    user_id: int,
    access_token: str,
    refresh_token: str,
    expires_in_seconds: int,
    scope: str = "",
    tenant_hint: str = "",
    account_email: str = "",
    account_display_name: str = "",
    provider: str = "microsoft_graph",
) -> None:
    expires_at = _utc_now() + timedelta(seconds=max(30, int(expires_in_seconds)))
    db.execute(
        """
        INSERT INTO user_mail_tokens
            (user_id, provider, access_token_enc, refresh_token_enc, expires_at_utc, scope, tenant_hint, account_email, account_display_name, updated_at)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, provider) DO UPDATE SET
            access_token_enc = excluded.access_token_enc,
            refresh_token_enc = excluded.refresh_token_enc,
            expires_at_utc = excluded.expires_at_utc,
            scope = excluded.scope,
            tenant_hint = excluded.tenant_hint,
            account_email = excluded.account_email,
            account_display_name = excluded.account_display_name,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            provider,
            _encrypt(app, access_token),
            _encrypt(app, refresh_token),
            _format_utc(expires_at),
            scope,
            tenant_hint,
            account_email,
            account_display_name,
        ),
    )


def remove_user_token(db, user_id: int, provider: str = "microsoft_graph") -> None:
    db.execute(
        "DELETE FROM user_mail_tokens WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    )


def token_is_expired(token_row: dict[str, Any] | None, skew_seconds: int = 90) -> bool:
    if not token_row:
        return True
    exp = token_row.get("expires_at_utc")
    if not exp:
        return True
    return _utc_now() >= (exp - timedelta(seconds=max(0, skew_seconds)))
