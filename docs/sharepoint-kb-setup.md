# SharePoint / Teams training folder for Ask MiNe

MiNe can sync documents from a SharePoint (Teams Files) folder into a local index so **Ask MiNe** answers onboarding and training questions from those files.

The folder you shared (FMI Offshore training / onboarding kits) is configured via a sharing URL and Microsoft Graph **application** permissions.

## 1) Entra app registration

Use the same app as mailbox Graph (or a dedicated one):

1. Microsoft Entra admin center → **App registrations** → your MiNe app.
2. **Certificates & secrets** → create a client secret if needed.
3. **API permissions** → **Microsoft Graph** → **Application** permissions (not delegated):
   - `Files.Read.All` **or** `Sites.Read.All`
4. Click **Grant admin consent** for the Hexaware tenant.
5. Note:
   - Application (client) ID
   - Client secret
   - Directory (tenant) ID — **required** (client credentials cannot use `common`)

## 2) MiNe `.env`

```env
MS_CLIENT_ID=<application-client-id>
MS_CLIENT_SECRET=<client-secret>
MS_TENANT=<directory-tenant-guid>

SHAREPOINT_KB_ENABLED=1
SHAREPOINT_KB_FOLDER_URL=https://hexawareonline.sharepoint.com/:f:/s/FMIOFFSHORE/...
# Optional:
# SHAREPOINT_KB_SYNC_ON_STARTUP=1
# SHAREPOINT_KB_SYNC_INTERVAL_HOURS=6
# SHAREPOINT_KB_MAX_FILES=200
# SHAREPOINT_KB_MAX_FILE_MB=25
```

Use the full SharePoint folder link (the `:f:` Teams/SharePoint sharing URL). Tracking query params like `email=` are stripped automatically.

## 3) Sync documents

### Option A — Live Graph (Teams/SharePoint)

Requires application permission + tenant GUID (see above).

```powershell
.\.venv\Scripts\python -m flask --app run:app sync-sharepoint --force
```

### Option B — Local mirror (works without Graph)

1. Download/copy files from the Teams channel folder.
2. Place them under `data/teams_training/` (subfolders OK).
3. Sync:

```powershell
.\.venv\Scripts\python -m flask --app run:app sync-sharepoint --force
```

Or as admin: **Security** → **Sync training docs now**.

Supported file types: PDF, DOCX, PPTX, XLSX, TXT, MD, CSV.

## 4) How Ask MiNe uses it

- Asking **Onboarding kit** / **Training** lists portal items **and** indexed Teams/SharePoint docs.
- Full (non-guest) users get SharePoint hits; guests do not.
- Source links open the file’s SharePoint `webUrl` when available (local mirror links use the folder URL).

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| “not configured” / tenant error | `MS_TENANT` is `common` — set the Hexaware tenant GUID |
| 403 / accessDenied on shares | App lacks admin-consented `Files.Read.All` / `Sites.Read.All`, or the app cannot redeem that link |
| 0 docs after sync | Folder empty of supported types, or size limits |
| Answers ignore new uploads | Re-run sync (`--force` or admin button) |

## Security

- App-only access reads whatever the application permission allows in the tenant — keep the secret private and prefer least privilege (`Sites.Selected` + site grant if your IT requires it).
- Do not commit `.env` or client secrets.
- Synced text lives in `mine.db` (`sharepoint_docs`); treat the DB as confidential.
