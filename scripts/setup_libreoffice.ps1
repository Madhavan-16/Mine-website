# Install LibreOffice for MiNe PDF attachment previews
# Run from the project root in PowerShell:
#   .\scripts\setup_libreoffice.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $ProjectRoot "tools"

Write-Host "MiNe — LibreOffice setup for attachment PDF previews" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot`n"

function Find-Soffice {
    $envPath = $env:LIBREOFFICE_PATH
    if ($envPath -and (Test-Path $envPath)) { return $envPath }

    $candidates = @(
        "${env:ProgramFiles}\LibreOffice\program\soffice.exe",
        "${env:ProgramFiles(x86)}\LibreOffice\program\soffice.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }

    if (Test-Path $ToolsDir) {
        Get-ChildItem -Path $ToolsDir -Recurse -Filter "soffice.exe" -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
    }
}

$existing = Find-Soffice
if ($existing) {
    Write-Host "LibreOffice already available:" -ForegroundColor Green
    Write-Host "  $existing"
    Write-Host "`nAdd to .env (optional):"
    Write-Host "  LIBREOFFICE_PATH=$existing"
    Write-Host "  BACKFILL_ATTACHMENT_PREVIEWS=1"
    exit 0
}

Write-Host "LibreOffice not found. Attempting winget install (may require admin)..." -ForegroundColor Yellow
try {
    winget install --id TheDocumentFoundation.LibreOffice `
        --accept-package-agreements --accept-source-agreements --disable-interactivity
} catch {
    Write-Host "winget install failed: $_" -ForegroundColor Red
}

$existing = Find-Soffice
if ($existing) {
    Write-Host "`nInstalled successfully:" -ForegroundColor Green
    Write-Host "  $existing"
    Write-Host "`nNext steps:"
    Write-Host "  1. Add to .env: LIBREOFFICE_PATH=$existing"
    Write-Host "  2. python scripts/backfill_attachment_previews.py"
    Write-Host "  3. Restart MiNe (python run.py)"
    exit 0
}

Write-Host @"

LibreOffice could not be installed automatically (winget blocked or admin required).

Manual options:
  A) IT / Software Center — install LibreOffice, then restart MiNe.
  B) winget (elevated PowerShell):
       winget install TheDocumentFoundation.LibreOffice
  C) Portable — extract LibreOffice Portable to:
       $ToolsDir\LibreOfficePortable
     (soffice.exe should be under App\libreoffice\program\)

After install, add to .env:
  LIBREOFFICE_PATH=C:\Program Files\LibreOffice\program\soffice.exe
  BACKFILL_ATTACHMENT_PREVIEWS=1

Then run:
  python scripts/backfill_attachment_previews.py
  python run.py

Note: PowerPoint slide text previews work without LibreOffice (built-in).
      LibreOffice adds full-fidelity PDF previews for Office uploads.

"@ -ForegroundColor Yellow

exit 1
