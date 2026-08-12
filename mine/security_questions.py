"""Security questions for password recovery (no email required)."""

from __future__ import annotations

import re
import secrets
from typing import Any

import bcrypt

from mine.db import get_db

REQUIRED_ANSWERS = 3

# Fixed catalog — users pick 3 distinct questions.
QUESTION_CATALOG: tuple[tuple[str, str], ...] = (
    ("school", "What was the name of your first school?"),
    ("nickname", "What was your childhood nickname?"),
    ("teacher", "What was your favorite teacher's last name?"),
    ("first_job_city", "In which city did you first work?"),
    ("pet", "What was the name of your first pet?"),
    ("street", "What street did you grow up on?"),
    ("sports", "What was your favorite sports team as a child?"),
    ("friend", "What is the first name of your best childhood friend?"),
    ("movie", "What was the first movie you saw in a theatre?"),
    ("food", "What is a dish your family cooked for celebrations?"),
)

_QUESTION_MAP = {qid: prompt for qid, prompt in QUESTION_CATALOG}


def ensure_security_questions_table(db=None) -> None:
    db = db or get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_security_answers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          question_id TEXT NOT NULL,
          answer_hash TEXT NOT NULL,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(user_id, question_id),
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_user_security_answers_user
          ON user_security_answers(user_id);
        """
    )
    db.commit()


def question_prompt(question_id: str) -> str:
    return _QUESTION_MAP.get((question_id or "").strip(), "Security question")


def catalog_choices(*, exclude_ids: set[str] | None = None) -> list[tuple[str, str]]:
    skip = exclude_ids or set()
    return [(qid, prompt) for qid, prompt in QUESTION_CATALOG if qid not in skip]


def normalize_answer(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    return s.strip()


def hash_answer(raw: str) -> str:
    norm = normalize_answer(raw)
    if not norm:
        raise ValueError("Answer cannot be empty.")
    return bcrypt.hashpw(norm.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_answer(raw: str, answer_hash: str) -> bool:
    norm = normalize_answer(raw)
    if not norm or not answer_hash:
        return False
    try:
        return bcrypt.checkpw(norm.encode("utf-8"), answer_hash.encode("utf-8"))
    except Exception:
        return False


def user_has_security_answers(db, user_id: int) -> bool:
    ensure_security_questions_table(db)
    row = db.execute(
        "SELECT COUNT(*) AS c FROM user_security_answers WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    return int(row["c"] or 0) >= REQUIRED_ANSWERS


def list_user_answers(db, user_id: int) -> list[dict[str, Any]]:
    ensure_security_questions_table(db)
    rows = db.execute(
        """
        SELECT question_id, answer_hash, updated_at
        FROM user_security_answers
        WHERE user_id = ?
        ORDER BY question_id
        """,
        (int(user_id),),
    ).fetchall()
    return [
        {
            "question_id": r["question_id"],
            "prompt": question_prompt(r["question_id"]),
            "answer_hash": r["answer_hash"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def save_user_answers(db, user_id: int, pairs: list[tuple[str, str]]) -> None:
    """Replace all answers for a user. pairs = [(question_id, raw_answer), ...] length 3."""
    ensure_security_questions_table(db)
    if len(pairs) != REQUIRED_ANSWERS:
        raise ValueError(f"Exactly {REQUIRED_ANSWERS} questions are required.")
    ids = [p[0] for p in pairs]
    if len(set(ids)) != REQUIRED_ANSWERS:
        raise ValueError("Choose three different questions.")
    for qid, _ in pairs:
        if qid not in _QUESTION_MAP:
            raise ValueError("Invalid security question.")
    uid = int(user_id)
    db.execute("DELETE FROM user_security_answers WHERE user_id = ?", (uid,))
    for qid, ans in pairs:
        db.execute(
            """
            INSERT INTO user_security_answers (user_id, question_id, answer_hash)
            VALUES (?, ?, ?)
            """,
            (uid, qid, hash_answer(ans)),
        )


def pick_challenge_question(db, user_id: int, *, avoid_id: str | None = None) -> dict[str, str] | None:
    answers = list_user_answers(db, user_id)
    if len(answers) < REQUIRED_ANSWERS:
        return None
    pool = [a for a in answers if a["question_id"] != avoid_id] or answers
    chosen = secrets.choice(pool)
    return {"question_id": chosen["question_id"], "prompt": chosen["prompt"]}


def verify_user_answer(db, user_id: int, question_id: str, raw_answer: str) -> bool:
    ensure_security_questions_table(db)
    row = db.execute(
        """
        SELECT answer_hash FROM user_security_answers
        WHERE user_id = ? AND question_id = ?
        """,
        (int(user_id), (question_id or "").strip()),
    ).fetchone()
    if not row:
        return False
    return verify_answer(raw_answer, row["answer_hash"])
