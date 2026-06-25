# Azure App Service deployment — previews & attachments

Pushing code to GitHub and deploying to Azure **does not copy your local uploads or database**. Previews work locally because the `.pptx` files exist on your machine; Azure starts with an empty `uploads/` folder unless you migrate data separately.

## Why previews work locally but not on Azure

| What | Local | Azure (default GitHub deploy) |
|------|-------|------------------------------|
| Application code | Yes | Yes (from GitHub) |
| `uploads/*.pptx` | Yes (on disk) | **No** — `uploads/*` is in `.gitignore` |
| `mine.db` (content + attachment rows) | Yes | **Often no** — not in repo / fresh DB on first run |
| Attachment `file_path` in DB | Windows paths like `C:\Users\...\uploads\...` | Those paths **do not exist** on Linux App Service |
| LibreOffice / PowerPoint | Optional locally | **Not installed** on App Service (PDF/slide PNG previews won't generate) |
| Visual PPTX preview (`preview-pptx-html`) | Works if file on disk | Works **only if** the same `.pptx` exists under `UPLOAD_FOLDER` |

The in-browser visual preview reads embedded SVG/PNG from the **original `.pptx` file on disk**. No file on Azure → empty or 404 preview.

## Fix: migrate data to Azure

### 1. Use persistent paths on App Service

In **Azure Portal → App Service → Configuration → Application settings**, set:

```
FLASK_SECRET_KEY=<strong-random-secret>
DATABASE_PATH=/home/data/mine.db
UPLOAD_FOLDER=/home/data/uploads
```

`/home` is persistent across restarts on App Service (unlike `/tmp`). Create the folder once via Kudu SSH or a startup script.

### 2. Copy your local database

From your dev machine (Kudu API, FTP, or Azure CLI):

- Copy `mine.db` → `/home/data/mine.db` on the app

Or re-create content by uploading attachments again through the Azure-hosted site (slower but simplest).

### 3. Copy all upload files

Copy **every file** from local `uploads/` to `/home/data/uploads/` on Azure.

Filenames must match what the DB expects (e.g. `68e1aaceb64546248a6d33e9fa3a087f_MINE_DTOW_-_Episode_2.pptx`). The app resolves Windows-style paths by falling back to `UPLOAD_FOLDER/<filename>`.

### 4. Restart the app

After copying DB + uploads, restart App Service. On startup, MiNe normalizes attachment paths and may attempt PDF/slide backfill (LibreOffice is usually unavailable on Azure — visual PPTX preview still works without it).

## Verify on Azure

1. Sign in to the Azure URL and open a knowledge item with a PPT attachment.
2. **Download original** — if this 404s, the file is missing from `UPLOAD_FOLDER`.
3. Open browser DevTools → Network → check `/files/<id>/preview-pptx-html` and `/files/<id>/pptx-asset/...` responses.

## Optional: Office Online embed

Office Online requires a **public HTTPS** URL to fetch the file. This usually works on Azure (unlike localhost). It still requires the physical file to exist at the signed download URL.

## Do not commit secrets or uploads

- Keep `uploads/` and `.env` out of Git (already in `.gitignore`).
- Set production secrets only in Azure Application settings.
- For team workflows, consider Azure Files mount or Blob storage for `UPLOAD_FOLDER` instead of manual copy.

## CI/CD note

`.github/workflows/main_mine.yml` deploys the repository artifact. Gitignored paths (`uploads/*`, `.env`) are **never** included in the build artifact.
