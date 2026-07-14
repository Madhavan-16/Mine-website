#!/usr/bin/env bash
# Align Azure App Service with MiNe data policy:
#   - UI / images / non-knowledge content: from local git push (wwwroot)
#   - Knowledge artefacts: bidirectional via /home/data/mine/knowledge
#
# Run in Azure Cloud Shell: https://shell.azure.com
set -euo pipefail

APP_NAME="${MINE_APP_NAME:-Mine}"

echo "Looking up resource group for App Service: $APP_NAME"
RG="$(az webapp list --query "[?name=='$APP_NAME'].resourceGroup | [0]" -o tsv)"
if [[ -z "$RG" || "$RG" == "null" ]]; then
  echo "ERROR: App Service '$APP_NAME' not found in this subscription."
  exit 1
fi
echo "Resource group: $RG"

echo "Clearing legacy full-store DATABASE_PATH / UPLOAD_FOLDER (git wwwroot is the live catalogue)..."
# delete if present (ignore errors when already absent)
az webapp config appsettings delete \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --setting-names DATABASE_PATH UPLOAD_FOLDER MINE_AZURE_DATA_ROOT \
  -o none 2>/dev/null || true

echo "Enabling knowledge-artefact mirror under /home/data/mine/knowledge..."
az webapp config appsettings set \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --settings \
    MINE_KNOWLEDGE_PERSIST="1" \
    MINE_KNOWLEDGE_PERSIST_ROOT="/home/data/mine/knowledge" \
  -o table

echo "Setting startup command to bash startup.sh..."
az webapp config set \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --startup-file "bash startup.sh"

echo "Current data-related app settings:"
az webapp config appsettings list \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --query "[?name=='DATABASE_PATH' || name=='UPLOAD_FOLDER' || name=='MINE_KNOWLEDGE_PERSIST' || name=='MINE_KNOWLEDGE_PERSIST_ROOT' || name=='FLASK_SECRET_KEY'].{name:name, value:value}]" \
  -o table

echo "Restarting app..."
az webapp restart --name "$APP_NAME" --resource-group "$RG"

echo "Done."
echo "Live DB/uploads = /home/site/wwwroot (updated by local git push)."
echo "Knowledge artefacts also mirror to /home/data/mine/knowledge (website ↔ local)."
echo "Optional merge tool: python tools/merge_catalog_into.py --modules knowledge --help"
