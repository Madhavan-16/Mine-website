# Azure App Service — persistent data & deployments



Your MiNe app URL (example):  

`https://mine-ffffhrdahfdhdcbx.centralindia-01.azurewebsites.net`



**Default workflow:** upload content locally → commit `mine.db` + `uploads/` → `git push` → Azure shows the same catalogue.



---



## Local upload → Azure deploy workflow



### 1. Create content locally



1. Run `python run.py` and open `http://127.0.0.1:5000`

2. Sign in → **Create content** (e.g. module **Case study**)

3. Upload files, fill fields, **Submit for review**, then **approve** as admin



Data is saved to:



| Item | Local path |

|------|------------|

| Database | `mine.db` (project root) |

| Attachments | `uploads/` |



### 2. Commit and push data with code



```powershell

cd c:\Users\2000137443\Desktop\MiNe

git add mine.db uploads/

git status

git commit -m "Add case studies and attachments"

git push origin main

```



GitHub Actions deploys the whole project to Azure (`/home/site/wwwroot/`). The live site reads the same `mine.db` and `uploads/` from that folder.



### 3. Verify on Azure



1. Open `/knowledge` (sign in if prompted)

2. Browse **Case studies** or other modules

3. Open a record and confirm **Download original** works



---



## Azure portal settings



**Configuration → Application settings**



| Name | Value |

|------|--------|

| `FLASK_SECRET_KEY` | Long random secret (keep stable across deploys) |



**Do not set** `DATABASE_PATH` or `UPLOAD_FOLDER`. The app uses `mine.db` and `uploads/` in the deployed project folder (same as local).

The latest code **automatically ignores** legacy portal values such as `/home/data/mine.db` on Azure. Still remove them in the portal for clarity — see [azure-portal-checklist.md](azure-portal-checklist.md).

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

| Application code | `/home/site/wwwroot/` |



| Not in git (by design) | Notes |

|------------------------|--------|

| `.env` / secrets | Use Azure Application settings |

| `uploads/.slide_previews/` | Regenerated on first preview view |

| Uploads done only on Azure | Lost on next deploy unless you download and commit |



---



## Deploy workflow diagram



```

Local: create content → mine.db + uploads/

              ↓

        git add + commit + push

              ↓

   GitHub Actions → Azure wwwroot (code + data)

              ↓

   https://…azurewebsites.net/knowledge

```



| Action | Updates Azure catalogue? |

|--------|--------------------------|

| Upload locally + `git push` | **Yes** |

| Upload only on Azure site (no git commit) | Yes until next deploy, then **lost** |

| `git push` without `mine.db` / `uploads/` | Code only — catalogue unchanged |



---



## Troubleshooting



| Symptom | Likely cause |

|---------|----------------|

| Case studies missing after deploy | Forgot `git add mine.db uploads/` before push |

| Still empty after push | Forgot `git add mine.db uploads/` before push |
| Still empty after push (rare) | Stale `/home/data` DB on disk — run `scripts/azure_fix_portal.sh` and redeploy with data in git |

| Download original 404 | File missing from `uploads/` in git |

| Preview empty | `.pptx` not committed; slide previews rebuild on first view |



**Log stream:** App Service → **Monitoring → Log stream**



---



## Optional: Azure-only uploads (not recommended)



If you create content directly on Azure without committing to git, it will be **overwritten** on the next deploy from GitHub. Prefer the local → git → deploy workflow above.



See also: [README.md](../README.md)


