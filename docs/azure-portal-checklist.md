# Azure portal checklist (copy/paste)

Use after pushing this repo. App example: `mine-ffffhrdahfdhdcbx.centralindia-01.azurewebsites.net`

## Application settings

| Name | Value |
|------|--------|
| `FLASK_SECRET_KEY` | *(your production secret)* |
| `DATABASE_PATH` | `/home/data/mine.db` |
| `UPLOAD_FOLDER` | `/home/data/uploads` |

## General settings

**Startup Command:**

```
bash startup.sh
```

## After save + restart

- [ ] Case studies visible on Azure site
- [ ] Download original works on an attachment
- [ ] Kudu shows files in `/home/data/uploads/`
- [ ] Kudu shows `/home/data/mine.db`

Full guide: [azure-deploy.md](azure-deploy.md)
