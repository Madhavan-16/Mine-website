# Azure App Service — persistent data & deployments

Your MiNe app URL (example):  
`https://mine-ffffhrdahfdhdcbx.centralindia-01.azurewebsites.net`

**GitHub only deploys code.** Case studies, attachments, and `mine.db` live on the server disk unless you configure persistent paths.

---

## One-time setup (recommended)

### Automatic (after you deploy this code)

On **Azure App Service**, MiNe detects `WEBSITE_SITE_NAME` and automatically:

- Uses **`/home/data/mine.db`** and **`/home/data/uploads/`** (persistent across redeploys)
- **Migrates once** from `/home/site/wwwroot/mine.db` and `uploads/` if persistent copies are empty

No portal changes are **required** for paths or migration after the next deploy.

### Optional portal settings (recommended for production)

**Azure Portal → App Service → Settings → Configuration**

| Name | Value |
|------|--------|
| `FLASK_SECRET_KEY` | Long random secret (keep stable across deploys) |
| `DATABASE_PATH` | `/home/data/mine.db` |
| `UPLOAD_FOLDER` | `/home/data/uploads` |

**General settings → Startup Command** (optional if Oryx already starts the app):

```
bash startup.sh
```

Then sign in and check:

1. Knowledge / case studies list shows your content
2. **Download original** on an attachment works
3. In-page preview works for `.pptx`

---

## What is saved automatically after setup

| You do this on Azure | Stored where |
|----------------------|--------------|
| Create / edit knowledge content | `/home/data/mine.db` |
| Upload `.pptx`, PDF, etc. | `/home/data/uploads/` |
| `git push` + GitHub deploy | **Code only** — data in `/home/data/` is kept |

Future uploads from the Azure website go to `/home/data/uploads` automatically. No extra step per file.

---

## Moving existing data (8 case studies already on Azure)

If you uploaded **before** setting `DATABASE_PATH` / `UPLOAD_FOLDER`:

**Option A — Automatic (recommended)**  
After steps 1–2 above, restart the app. `startup.sh` copies `wwwroot/mine.db` and `wwwroot/uploads/*` into `/home/data/` if persistent files are still empty.

**Option B — Manual (Kudu)**  

1. **Development Tools → Advanced Tools → Go**
2. **SSH** or **Bash**
3. Run:

```bash
mkdir -p /home/data/uploads
cp /home/site/wwwroot/mine.db /home/data/mine.db 2>/dev/null || true
cp -r /home/site/wwwroot/uploads/* /home/data/uploads/ 2>/dev/null || true
```

4. Restart the app from Overview.

---

## Backup Azure data (recommended)

Git does **not** back up uploads or the database.

### Manual backup via Kudu

1. Advanced Tools → **File Manager** (or SSH)
2. Download:
   - `/home/data/mine.db`
   - All files under `/home/data/uploads/`
3. Store on your PC or team file share.

Repeat monthly or before major changes.

### Use on local dev

Copy downloaded files to your PC project:

- `mine.db` → `c:\Users\...\MiNe\mine.db`
- `uploads\*` → `c:\Users\...\MiNe\uploads\`

Then run `python run.py`. This is a **file copy**, not `git pull`.

### Azure App Service Backup (optional)

If your plan supports it: **Backup** blade → configure Storage Account backup. Ask IT whether this is enabled in your subscription.

---

## Deploy workflow (code vs data)

```
Local code changes → git push → GitHub Actions → Azure redeploy
                                      ↓
                            /home/site/wwwroot/  (app code replaced)
                            /home/data/          (database + uploads KEPT)
```

| Action | Affects code | Affects case studies / files |
|--------|--------------|------------------------------|
| `git push` + deploy | Yes | No (with `/home/data` settings) |
| `git pull` on PC | Local code only | Does not sync Azure data |
| Upload on Azure site | No | Yes — saved under `/home/data/` |

---

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Case studies missing after deploy | `DATABASE_PATH` not set; data was only in `wwwroot` |
| Download original 404 | File not in `UPLOAD_FOLDER`; check `/home/data/uploads/` in Kudu |
| Preview empty | Same — missing `.pptx` on disk |
| App won't start | Startup Command must be `bash startup.sh`; check **Log stream** |

**Log stream:** App Service → **Monitoring → Log stream**

---

## Do not commit to Git

- `uploads/*` (gitignored)
- `mine.db` with production data
- `.env` / secrets — use Azure Application settings only

See also: [README.md](../README.md) (Docker volume example for local persistence).
