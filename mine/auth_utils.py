from functools import wraps

from flask import abort, g, redirect, request, session, url_for

from mine.db import get_db


def login_next_url() -> str:
    """Preserve path and query string for post-login return (search params, filters, etc.)."""
    target = (request.full_path or request.path or "").strip()
    if target.endswith("?"):
        target = target[:-1]
    if not target.startswith("/") or target.startswith("//"):
        return request.path or "/"
    return target


def safe_login_next(raw: str | None) -> str | None:
    """Validate a post-login redirect target (relative path only)."""
    target = (raw or "").strip()
    if target.endswith("?"):
        target = target[:-1]
    if not target.startswith("/") or target.startswith("//"):
        return None
    return target or None


def load_current_user():
    if "_mine_user" in g:
        return g._mine_user
    uid = session.get("user_id")
    if not uid:
        g._mine_user = None
        return None
    row = get_db().execute(
        "SELECT * FROM users WHERE id = ? AND is_active = 1",
        (uid,),
    ).fetchone()
    g._mine_user = row
    return row


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not load_current_user():
            return redirect(url_for("auth.login", next=login_next_url()))
        return f(*args, **kwargs)

    return wrapped


def roles_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user = load_current_user()
            if not user:
                return redirect(url_for("auth.login", next=login_next_url()))
            if user["role"] not in roles:
                abort(403)
            return f(*args, **kwargs)

        return wrapped

    return deco
