# Azure portal checklist (copy/paste)

App: `mine-ffffhrdahfdhdcbx.centralindia-01.azurewebsites.net` · App Service name: **Mine**

---

## Data policy

- **UI / images / text / layout / non-knowledge** → update from **local git push** only (`wwwroot`)
- **Knowledge artefacts** → **website only** (create / approve / edit on Azure; durable mirror at `/home/data/mine/knowledge`)

---

## Automatic (after you deploy the latest code)

MiNe **ignores** legacy portal `DATABASE_PATH` / `UPLOAD_FOLDER` when they point at `/home/data/mine`. Live catalogue:

| Item | Path on Azure |
|------|----------------|
| Database | `/home/site/wwwroot/mine.db` |
| Uploads | `/home/site/wwwroot/uploads/` |
| Knowledge mirror | `/home/data/mine/knowledge/` |

---

## One-time portal cleanup (recommended)

### Option A — Azure Cloud Shell (fastest)

1. Open [Azure Cloud Shell](https://shell.azure.com) (Bash).
2. Run:

```bash
curl -sL https://raw.githubusercontent.com/Madhavan-16/Mine-website/main/scripts/azure_fix_portal.sh | bash
```

Or from your cloned repo:

```bash
bash scripts/azure_fix_portal.sh
```

This removes legacy `DATABASE_PATH` / `UPLOAD_FOLDER`, enables the knowledge mirror, sets startup to `bash startup.sh`, and restarts the app.

### Option B — Azure Portal (manual)

1. **Configuration → Application settings**
2. **Delete** `DATABASE_PATH`, `UPLOAD_FOLDER`, `MINE_AZURE_DATA_ROOT` if present
3. **Add/set:**
   - `MINE_KNOWLEDGE_PERSIST` = `1`
   - `MINE_KNOWLEDGE_PERSIST_ROOT` = `/home/data/mine/knowledge`
4. **General settings → Startup Command** = `bash startup.sh`
5. **Save** and restart

---

## After deploy checklist

- [ ] Home / journey / projects UI matches local git push
- [ ] Static images and journey assets match local push
- [ ] Create knowledge on website → Submit for review → Approve & publish works
- [ ] Approved item appears under Knowledge repository (PENDING badge gone)
- [ ] Kudu → `/home/data/mine/knowledge/` has `knowledge.db` after website knowledge upload/approve
- [ ] After a UI-only git push + restart, website knowledge is still present

Full guide: [azure-deploy.md](azure-deploy.md)
