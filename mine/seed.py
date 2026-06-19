import bcrypt
from mine.db import get_db


def seed_if_empty():
    db = get_db()
    row = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()
    if row and row["c"] > 0:
        return
    password = b"ChangeMe123!"
    pw_hash = bcrypt.hashpw(password, bcrypt.gensalt()).decode("utf-8")
    db.execute(
        """
        INSERT INTO users (username, email, password_hash, display_name, role, is_active)
        VALUES (?, ?, ?, ?, 'admin', 1)
        """,
        ("admin", "admin@hexaware.local", pw_hash, "MiNe Administrator"),
    )
    db.commit()
