$ErrorActionPreference = "Stop"
Set-Location -LiteralPath "$PSScriptRoot\frontend"
if (-not (Test-Path "node_modules")) { Write-Host "Dependencias frontend ausentes: execute npm install primeiro."; exit 1 }
npm run dev
