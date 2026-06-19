from functools import wraps

from flask import abort, g, redirect, request, session, url_for

from mine.db import get_db


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
            return redirect(url_for("auth.login", next=request.path))
        return f(*args, **kwargs)

    return wrapped


def roles_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user = load_current_user()
            if not user:
                return redirect(url_for("auth.login", next=request.path))
            if user["role"] not in roles:
                abort(403)
            return f(*args, **kwargs)

        return wrapped

    return deco
