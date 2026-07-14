# Align Azure App Service with MiNe data policy (PowerShell wrapper).
# Prefer scripts/azure_fix_portal.sh in Azure Cloud Shell (Bash).

Write-Host "This script requires Azure CLI (az). Prefer scripts/azure_fix_portal.sh in Cloud Shell." -ForegroundColor Yellow

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: 'az' not found. Open https://shell.azure.com and run scripts/azure_fix_portal.sh instead." -ForegroundColor Red
    exit 1
}

$AppName = if ($env:MINE_APP_NAME) { $env:MINE_APP_NAME } else { "Mine" }
Write-Host "Looking up resource group for App Service: $AppName"
$Rg = az webapp list --query "[?name=='$AppName'].resourceGroup | [0]" -o tsv
if (-not $Rg -or $Rg -eq "null") {
    Write-Host "ERROR: App Service '$AppName' not found." -ForegroundColor Red
    exit 1
}

Write-Host "Clearing legacy DATABASE_PATH / UPLOAD_FOLDER..."
az webapp config appsettings delete --name $AppName --resource-group $Rg --setting-names DATABASE_PATH UPLOAD_FOLDER MINE_AZURE_DATA_ROOT -o none 2>$null

Write-Host "Enabling knowledge-artefact mirror..."
az webapp config appsettings set --name $AppName --resource-group $Rg --settings `
  MINE_KNOWLEDGE_PERSIST="1" `
  MINE_KNOWLEDGE_PERSIST_ROOT="/home/data/mine/knowledge" `
  -o table

az webapp config set --name $AppName --resource-group $Rg --startup-file "bash startup.sh"
az webapp restart --name $AppName --resource-group $Rg

Write-Host "Done. Live catalogue = wwwroot from local git push; knowledge also mirrors under /home/data/mine/knowledge." -ForegroundColor Green
