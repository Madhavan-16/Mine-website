# MiNe (Mining Intelligence and Knowledge Enablement)

End-to-end Phase 1 portal for the MiNe program specification: **Flask + SQLite + server-rendered HTML**, with moderation, RBAC, FTS search, local uploads, and **public account context** page at `/program/` (Freeport KYC only; other spec sections are implementation reference, not shown in the portal).

## Project layout (individual files)

| Area | Files |
|------|--------|
| **Python (app)** | `run.py`, `wsgi.py`, `mine/__init__.py`, `mine/config.py`, `mine/db.py`, `mine/schema.sql`, `mine/auth.py`, `mine/auth_utils.py`, `mine/main.py`, `mine/content.py`, `mine/projects.py`, `mine/search.py`, `mine/admin.py`, `mine/mail.py`, `mine/reference.py` (public Freeport KYC route only), `mine/services.py`, `mine/seed.py`, `mine/fts.py` |
| **HTML (Jinja templates)** | `templates/base.html`, `templates/landing.html`, `templates/journey.html`, … plus `templates/program/` (`fmi_know_your_customer.html`, layout partials) |
| **CSS** | `static/css/variables.css`, `static/css/main.css`, `static/css/reference.css`, `static/css/landing.css` |
| **Config** | `requirements.txt`, `.env.example`, `.gitignore`, `Dockerfile`, `.dockerignore` |

Public account context URLs (no login):

- `/program/` — redirects to Freeport KYC
- `/program/fmi-know-your-customer` — Freeport — Know your customer (Section 2)
- `/program/background-context` — **301 redirect** to KYC (legacy URL; page removed)

## View without Python (static HTML)

Open the **`static_site`** folder and double-click **`index.html`**, or open it in your browser.

- Includes: landing, journey, and **program/fmi-know-your-customer.html** (mirrors the public `/program/` KYC page).
- Does **not** include login, database, search, or uploads — those need `python run.py` or Docker.

See **`static_site/README.txt`** for details.

## Prerequisites

- Python 3.11+ on your PATH as `python` (Windows: install from python.org or use your corporate Python distribution)

## Setup

```powershell
cd MiNe
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Initialize the database (optional if you rely on first-run auto-create):

```powershell
.\.venv\Scripts\python -m flask --app run init-db
```

## Run (development)

```powershell
.\.venv\Scripts\python run.py
```

Open `http://127.0.0.1:5000`.

## Outbound email (optional)

MiNe can send mail when `MAIL_*` variables are set (see `.env.example`). Admins use **Settings → Send email** (`/admin/mail`) or **Send email** from **User management**.

- **Local / no SMTP server:** set `MAIL_ENABLED=1`, `MAIL_DEFAULT_SENDER=...`, and `MAIL_DUMMY=1`. Messages are appended to `logs/mail-outbox.log` so the UI works without Microsoft or Gmail credentials.
- **Production:** set `MAIL_DUMMY=0` (or remove it), set `MAIL_SERVER`, TLS/SSL flags, and usually `MAIL_USERNAME` / `MAIL_PASSWORD`, matching your provider (for example Microsoft 365 SMTP).

For **Outlook / Microsoft 365** mailboxes, see [docs/outlook-smtp.md](docs/outlook-smtp.md) (SMTP AUTH, MFA app passwords, and troubleshooting).

By default, admin compose accepts **any syntactically valid address**. Set `MAIL_OPEN_RECIPIENTS=0` to restrict to **active user emails** plus `MAIL_EXTRA_ALLOWLIST`. Use `MAIL_SMTP_DEBUG=1` for verbose SMTP logs on stderr. Set `MAIL_NOTIFY_ON_PENDING=1` to also email admins/moderators when an item enters the moderation queue (in addition to in-app notifications).

## Outlook mailbox via Microsoft Graph (admin)

MiNe also supports admin mailbox integration using **Microsoft Graph API** and OAuth 2.0 Authorization Code flow. This is separate from SMTP:

- Users authenticate with Microsoft sign-in and consent.
- MiNe stores only encrypted access/refresh tokens (no Outlook password storage).
- Admin pages are available under `/admin/mailbox/*`:
  - Inbox, Sent, Drafts, Trash
  - Message detail
  - Compose with To/CC/BCC + attachments

Setup instructions are in [docs/graph-mail-setup.md](docs/graph-mail-setup.md).

## Run (production-style, cross-platform)

[Waitress](https://docs.pylonsproject.org/projects/waitress/) is included for Windows/Linux/macOS:

```powershell
.\.venv\Scripts\waitress-serve --host=0.0.0.0 --port=8080 wsgi:app
```

On Linux with Gunicorn (install separately if desired):

```bash
gunicorn -w 4 -b 0.0.0.0:8080 wsgi:app
```

## Docker

```bash
docker build -t mine .
docker run --rm -p 8080:8080 -e FLASK_SECRET_KEY=change-me mine
```

Mount a volume for persistence (database + uploads), for example:

```bash
docker run --rm -p 8080:8080 -e FLASK_SECRET_KEY=change-me -v mine_data:/app/data -e DATABASE_PATH=/app/data/mine.db -e UPLOAD_FOLDER=/app/data/uploads mine
```

(Adjust paths to match your hosting policy.)

## Bootstrap credentials

On first database creation, a default administrator is created:

- Username: `admin`
- Password: `ChangeMe123!`

Change this immediately via **Admin → Users** after signing in.

## Notes

- Database defaults to `mine.db` in the project root (`DATABASE_PATH`).
- Uploads use `uploads/` (`UPLOAD_FOLDER`, `MAX_CONTENT_LENGTH` in `.env.example`).
- **Commit `mine.db` and `uploads/` to git** when you want local content to appear on Azure after deploy — see [docs/azure-deploy.md](docs/azure-deploy.md).
- The **journey** page (`/journey`) and all **`/program/*`** pages are public; the operational portal remains behind login.
