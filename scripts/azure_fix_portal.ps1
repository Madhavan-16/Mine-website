# One-time Azure portal fix for MiNe git-deploy workflow.
# Run in Azure Cloud Shell: https://shell.azure.com
#
#   curl -sL https://raw.githubusercontent.com/Madhavan-16/Mine-website/main/scripts/azure_fix_portal.sh | bash
# Or from a cloned repo:
#   bash scripts/azure_fix_portal.sh

param(
    [string]$AppName = "Mine"
)

Write-Host "This script requires Azure CLI (az). Use Azure Cloud Shell if az is not installed locally." -ForegroundColor Yellow

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
Write-Host "Removing DATABASE_PATH and UPLOAD_FOLDER (if set)..."
az webapp config appsettings delete --name $AppName --resource-group $rg --setting-names DATABASE_PATH UPLOAD_FOLDER 2>$null

Write-Host "Setting startup command..."
az webapp config set --name $AppName --resource-group $rg --startup-file "bash startup.sh"

Write-Host "Restarting app..."
az webapp restart --name $AppName --resource-group $rg

Write-Host "Done." -ForegroundColor Green
