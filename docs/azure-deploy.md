# Azure App Service — deployments & data policy

Your MiNe app URL (example):  
`https://mine-ffffhrdahfdhdcbx.centralindia-01.azurewebsites.net`

## Data policy (important)

| What | How it updates |
|------|----------------|
| UI, CSS/JS, images, text boxes, journey assets, projects config, users, non-knowledge content | **Local → git push only** (wwwroot) |
| Knowledge repository artefacts (KYC, KYA, term of the week, newsletter, case studies, RFP snippets, blogs & files) | **Website only** — create, edit, approve/reject on the live portal |

Live paths on Azure:

| Item | Path |
|------|------|
| Database (UI + non-knowledge) | `/home/site/wwwroot/mine.db` |
| Uploads (non-knowledge + mirrored knowledge files) | `/home/site/wwwroot/uploads/` |
| Knowledge mirror (durable) | `/home/data/mine/knowledge/` |

Website knowledge uploads and approvals are mirrored under `/home/data/mine/knowledge`. After every deploy/restart, that mirror is merged into wwwroot so a UI-only git push cannot wipe knowledge.

**Do not rely on pushing local `mine.db` / `uploads/` for knowledge series.** Knowledge is managed on the website.

---

## Website knowledge workflow

1. Sign in on Azure → **Create content** → choose a knowledge series → **Submit for review**
2. Moderator/admin opens the item → **Approve & publish** (or return with feedback)
3. Approved items appear in **Knowledge repository** and stay durable via `/home/data/mine/knowledge`

Edit knowledge on the website (admin for approved items). Attachments follow the same path.

---

## Local git push (UI / assets only)

```powershell
cd c:\Users\2000137443\Desktop\MiNe
git add static/ templates/ mine/ docs/
git status
git commit -m "UI / portal updates"
git push origin main
```

Avoid committing knowledge-only changes from a local `mine.db` unless you intend to seed non-knowledge data. After deploy, startup merges the knowledge mirror into live so website knowledge remains.

---

## Azure settings

| Setting | Value |
|---------|--------|
| `MINE_KNOWLEDGE_PERSIST` | `1` (default) |
| `MINE_KNOWLEDGE_PERSIST_ROOT` | `/home/data/mine/knowledge` |

**Do not set** `DATABASE_PATH` or `UPLOAD_FOLDER` to `/home/data/mine`. Those legacy settings are ignored; the live site uses wwwroot plus the knowledge mirror.

Run once after deploy if needed:

```bash
bash scripts/azure_fix_portal.sh
```

---

## Flow diagram

```
Local UI / images / code  →  git push  →  /home/site/wwwroot/
Knowledge on website      ↔  /home/data/mine/knowledge  →  merged into wwwroot on startup
```

| Action | Result |
|--------|--------|
| Push UI / images / code | Website UI updates; knowledge mirror preserved and re-applied |
| Upload + approve knowledge on Azure | Published on site and durable across deploys |
| Push local `mine.db` with old knowledge | Overwritten on startup by website knowledge mirror |

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Approve seems to do nothing | Hard-refresh; you should land on the item without PENDING. Confirm role is admin/moderator |
| Approved item missing after deploy | Kudu → `/home/data/mine/knowledge/` has `knowledge.db`; app logs for “Knowledge persist” |
| Download 404 for knowledge file | File should exist under `/home/data/mine/knowledge/uploads/` and be copied into wwwroot `uploads/` |
| CSRF / 400 on Approve | Sign out/in and retry; ensure cookies work on the Azure hostname |
