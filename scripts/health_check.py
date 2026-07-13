"""Broader route and workflow health check (no external network)."""
from __future__ import annotations

import sys

from mine import create_app
from mine.db import get_db


def main() -> int:
    app = create_app()
    client = app.test_client()
    errors: list[str] = []

    def get(path: str, *, expect=(200, 302), label: str | None = None):
        r = client.get(path, follow_redirects=False)
        if r.status_code not in expect:
            errors.append(f"GET {label or path} -> {r.status_code} (expected {expect})")
        return r

    def get_follow(path: str, *, expect=200):
        r = client.get(path, follow_redirects=True)
        if r.status_code != expect:
            errors.append(f"GET {path} (follow) -> {r.status_code}")
        return r

    # Guest public routes
    get("/")
    get("/login")
    get("/program/fmi-know-your-customer", expect=(200, 302))
    get("/journey", expect=(200, 302))

    landing = get_follow("/")
    if b"landing-hero" not in landing.data:
        errors.append("Landing page missing hero markup")
    if b"auth-card" in landing.data:
        errors.append("Landing page unexpectedly shows auth card")

    login = get_follow("/login")
    if b"auth-card" not in login.data:
        errors.append("Login page missing auth card")
    if b'data-aos="fade-up"' in login.data:
        errors.append("Login still uses data-aos (visibility risk)")
    if b"site-motion-prep" in login.data:
        errors.append("Login still injects site-motion-prep script")

    # Signed-in user workflows
    with app.app_context():
        db = get_db()
        admin = db.execute(
            "SELECT id FROM users WHERE role = 'admin' AND is_active = 1 LIMIT 1"
        ).fetchone()
        user = db.execute(
            "SELECT id FROM users WHERE role = 'user' AND is_active = 1 LIMIT 1"
        ).fetchone()
        admin_id = int(admin["id"]) if admin else 1
        user_id = int(user["id"]) if user else 1

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    get("/dashboard")
    get("/welcome")
    get("/knowledge")
    get("/search")
    get("/my/submissions", expect=(200, 302))

    # Non-admin should not reach content catalogue directly (redirect)
    r_content = get("/content", expect=(200, 302))
    if r_content.status_code == 302 and "/knowledge" not in (r_content.headers.get("Location") or ""):
        loc = r_content.headers.get("Location", "")
        if "/login" not in loc:
            errors.append(f"Non-admin /content redirect unexpected: {loc}")

    with client.session_transaction() as sess:
        sess["user_id"] = admin_id

    get("/dashboard")
    get("/content", expect=(200, 302))
    get("/admin/moderation", expect=(200, 302))
    get("/admin/users", expect=(200, 302))
    get("/admin/analytics", expect=(200, 302))

    # Context helpers
    with app.app_context():
        from mine.main import _landing_page_context

        with app.test_request_context("/"):
            ctx = _landing_page_context(get_db(), None)
        if len(ctx["quick_access"]) != 9:
            errors.append(f"Guest quick_access tiles: {len(ctx['quick_access'])} (expected 9)")

    if errors:
        print("HEALTH CHECK FAILED:")
        for e in errors:
            print(" -", e)
        return 1

    print("HEALTH CHECK OK — core routes and workflows responded as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
