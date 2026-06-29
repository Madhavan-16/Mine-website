# Azure portal checklist (copy/paste)



App: `mine-ffffhrdahfdhdcbx.centralindia-01.azurewebsites.net` · App Service name: **Mine**



---



## Automatic (after you deploy the latest code)



MiNe **ignores** portal `DATABASE_PATH` and `UPLOAD_FOLDER` on Azure App Service. It always uses:



| Item | Path on Azure |

|------|----------------|

| Database | `/home/site/wwwroot/mine.db` |

| Uploads | `/home/site/wwwroot/uploads/` |



So even if old portal settings point at `/home/data/...`, the app reads the git-deployed files instead.



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



This removes `DATABASE_PATH` / `UPLOAD_FOLDER`, sets startup to `bash startup.sh`, and restarts the app.



### Option B — Azure Portal (manual)



1. **Azure Portal** → **App Service** → **Mine**

2. **Settings** → **Environment variables** (or **Configuration** → **Application settings**)

3. **Delete** these if present:

   - `DATABASE_PATH`

   - `UPLOAD_FOLDER`

4. **Keep** (or add):

   - `FLASK_SECRET_KEY` = your production secret

5. **Settings** → **Configuration** → **General settings**

6. **Startup Command:**



```

bash startup.sh

```



7. **Save** → **Restart** the app.



---



## Verify settings



In **Environment variables**, you should see:



| Setting | Expected |

|---------|----------|

| `FLASK_SECRET_KEY` | Set (hidden value) |

| `DATABASE_PATH` | **Not present** |

| `UPLOAD_FOLDER` | **Not present** |



In **General settings**:



| Setting | Expected |

|---------|----------|

| Startup Command | `bash startup.sh` |



After deploy with `mine.db` + `uploads/` committed:



- [ ] `/knowledge` shows your approved content

- [ ] Kudu → `/home/site/wwwroot/mine.db` exists

- [ ] Kudu → `/home/site/wwwroot/uploads/` contains your files

- [ ] Log stream shows `Azure data paths: DATABASE=/home/site/wwwroot/mine.db` (no “ignoring portal” warning after cleanup)



Full guide: [azure-deploy.md](azure-deploy.md)


