# Azure App Service — deployments & data policy

Your MiNe app URL (example):  
`https://mine-ffffhrdahfdhdcbx.centralindia-01.azurewebsites.net`

## Data policy (important)

| What | How it updates |
|------|----------------|
| UI, CSS/JS, images, journey assets, projects config, users, non-knowledge content | **Local → git push only** (wwwroot) |
| Knowledge repository artefacts (KYC, KYA, term of the week, newsletter, case studies, RFP snippets, blogs & files) | **Both ways** — local push *and* durable mirror of website uploads |

Live catalogue paths on Azure:

| Item | Path |
|------|------|
| Database | `/home/site/wwwroot/mine.db` |
| Uploads | `/home/site/wwwroot/uploads/` |
| Knowledge mirror (Azure only) | `/home/data/mine/knowledge/` |

Website knowledge uploads are mirrored under `/home/data/mine/knowledge` and merged back into wwwroot after each deploy so they are not wiped by a UI-only push.

---

## Local upload → Azure deploy workflow

### 1. Create content locally

1. Run `python run.py` and open `http://127.0.0.1:5000`
2. Sign in → create / edit content and assets as usual

Data is saved to:

| Item | Local path |
|------|------------|
| Database | `mine.db` (project root) |
| Attachments | `uploads/` |

### 2. Commit and push (code + any catalogue data you want on Azure)

```powershell
cd c:\Users\2000137443\Desktop\MiNe
git add mine.db uploads/
git status
git commit -m "Add catalogue / attachments"
git push origin main
```

GitHub Actions deploys to `/home/site/wwwroot/`. That is the live source of truth for UI and non-knowledge content.

### 3. Verify on Azure

1. Open `/knowledge` (sign in if prompted)
2. Confirm records and **Download original**

---

## Azure portal settings

**Configuration → Application settings**

| Name | Value |
|------|--------|
| `FLASK_SECRET_KEY` | Long random secret (keep stable across deploys) |
| `MINE_KNOWLEDGE_PERSIST` | `1` (default) |
| `MINE_KNOWLEDGE_PERSIST_ROOT` | `/home/data/mine/knowledge` |

**Do not set** `DATABASE_PATH` or `UPLOAD_FOLDER` to `/home/data/mine`. Those legacy settings are ignored; the live site uses the git-deployed wwwroot DB/uploads.

**One-time fix (Azure Cloud Shell):** `bash scripts/azure_fix_portal.sh`

**General settings → Startup Command:**

```
bash startup.sh
```

---

## What gets deployed

| Included in git deploy | Path on Azure |
|------------------------|---------------|
| `mine.db` | `/home/site/wwwroot/mine.db` |
| `uploads/*` (except `.slide_previews/`) | `/home/site/wwwroot/uploads/` |
| Application code / static images / UI | `/home/site/wwwroot/` |

| Durable outside git | Notes |
|---------------------|--------|
| `/home/data/mine/knowledge/` | Knowledge artefacts uploaded on the website; merged into wwwroot on startup |
| `.env` / secrets | Use Azure Application settings |
| `uploads/.slide_previews/` | Regenerated on first preview view |

---

## Deploy workflow

```
Local UI / assets / non-knowledge content
        ↓ git push
   Azure wwwroot (source of truth)

Knowledge on website  ↔  /home/data/mine/knowledge  ↔  wwwroot after deploy
Knowledge on local    →  git push mine.db + uploads (and/or merge tool)
```

| Action | Result |
|--------|--------|
| Push UI / images / code | Website UI updates; knowledge mirror preserved |
| Upload knowledge on Azure | Survives next deploy (knowledge mirror) |
| Upload knowledge locally + push `mine.db` / `uploads/` | Appears on Azure |
| Push without `mine.db` / `uploads/` | Code/UI only; existing wwwroot catalogue unchanged until next data push |

Optional: `python tools/merge_catalog_into.py --modules knowledge --help`

---

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| UI not updating | Code not pushed / Actions failed |
| Case studies missing after deploy | Forgot `git add mine.db uploads/` *and* no knowledge mirror yet |
| Still reading old `/home/data` catalogue | Run `scripts/azure_fix_portal.sh` to clear legacy `DATABASE_PATH` |
| Download original 404 | File missing from `uploads/` in git (or knowledge mirror for Azure-only uploads) |

**Log stream:** App Service → **Monitoring → Log stream**

See also: [azure-portal-checklist.md](azure-portal-checklist.md) · [README.md](../README.md)
