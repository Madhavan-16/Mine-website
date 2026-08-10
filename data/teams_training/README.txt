Copy onboarding/training files from the FMI Offshore Teams/SharePoint folder into this directory (PDF, DOCX, PPTX, XLSX, TXT, MD, CSV). Subfolders are included.

Then run: flask sync-sharepoint --force
Or use Admin → Security → Sync training docs now.

Live Graph sync also works once MS_CLIENT_ID / MS_CLIENT_SECRET / MS_TENANT (GUID) are set with Files.Read.All application permission + admin consent.
