#!/usr/bin/env bash
# Apply Azure App Service settings so live content survives git deploy.
# Data lives under /home/data/mine (persistent). Code stays in wwwroot.
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

echo "Setting persistent DATABASE_PATH and UPLOAD_FOLDER under /home/data/mine..."
az webapp config appsettings set \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --settings \
    DATABASE_PATH="/home/data/mine/mine.db" \
    UPLOAD_FOLDER="/home/data/mine/uploads" \
    MINE_AZURE_DATA_ROOT="/home/data/mine" \
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
  --query "[?name=='DATABASE_PATH' || name=='UPLOAD_FOLDER' || name=='MINE_AZURE_DATA_ROOT' || name=='FLASK_SECRET_KEY'].{name:name, value:value}]" \
  -o table

echo "Restarting app..."
az webapp restart --name "$APP_NAME" --resource-group "$RG"

echo "Done."
echo "Website uploads now persist in /home/data/mine across git pushes."
echo "Local machine still uses project-root mine.db + uploads/."
echo "To publish local-only catalogue items onto Azure, see: python tools/merge_catalog_into.py --help"
