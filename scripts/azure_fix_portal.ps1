# One-time Azure portal fix: persistent data under /home/data/mine (survives git deploy).
# Prefer bash in Cloud Shell:
#   bash scripts/azure_fix_portal.sh

param(
    [string]$AppName = "Mine"
)

Write-Host "This script requires Azure CLI (az). Prefer scripts/azure_fix_portal.sh in Cloud Shell." -ForegroundColor Yellow

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: 'az' not found. Open https://shell.azure.com and run scripts/azure_fix_portal.sh instead." -ForegroundColor Red
    exit 1
}

$rg = az webapp list --query "[?name=='$AppName'].resourceGroup | [0]" -o tsv
if (-not $rg) {
    Write-Host "ERROR: App Service '$AppName' not found." -ForegroundColor Red
    exit 1
}

Write-Host "Resource group: $rg"
Write-Host "Setting persistent DATABASE_PATH / UPLOAD_FOLDER..."
az webapp config appsettings set --name $AppName --resource-group $rg --settings `
  DATABASE_PATH="/home/data/mine/mine.db" `
  UPLOAD_FOLDER="/home/data/mine/uploads" `
  MINE_AZURE_DATA_ROOT="/home/data/mine"

Write-Host "Setting startup command..."
az webapp config set --name $AppName --resource-group $rg --startup-file "bash startup.sh"

Write-Host "Restarting app..."
az webapp restart --name $AppName --resource-group $rg

Write-Host "Done. Live data persists under /home/data/mine." -ForegroundColor Green
