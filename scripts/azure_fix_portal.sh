#!/usr/bin/env bash
# Apply recommended Azure App Service settings for MiNe git-deploy workflow.
# Run in Azure Cloud Shell (https://shell.azure.com) while logged into your subscription.
set -euo pipefail

APP_NAME="${MINE_APP_NAME:-Mine}"

echo "Looking up resource group for App Service: $APP_NAME"
RG="$(az webapp list --query "[?name=='$APP_NAME'].resourceGroup | [0]" -o tsv)"
if [[ -z "$RG" || "$RG" == "null" ]]; then
  echo "ERROR: App Service '$APP_NAME' not found in this subscription."
  exit 1
fi
echo "Resource group: $RG"

echo "Removing legacy DATABASE_PATH and UPLOAD_FOLDER portal settings (if present)..."
az webapp config appsettings delete \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --setting-names DATABASE_PATH UPLOAD_FOLDER \
  2>/dev/null || true

echo "Setting startup command to bash startup.sh..."
az webapp config set \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --startup-file "bash startup.sh"

echo "Current app settings (data paths should be absent):"
az webapp config appsettings list \
  --name "$APP_NAME" \
  --resource-group "$RG" \
  --query "[?name=='DATABASE_PATH' || name=='UPLOAD_FOLDER' || name=='FLASK_SECRET_KEY'].{name:name, value:value}]" \
  -o table

echo "Restarting app..."
az webapp restart --name "$APP_NAME" --resource-group "$RG"

echo "Done. MiNe will use mine.db and uploads/ from the deployed project folder."
