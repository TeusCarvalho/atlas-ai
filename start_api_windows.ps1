$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Write-Error 'Ambiente Python ausente. Rode: py -m venv .venv'
    exit 1
}
# Carrega somente variaveis permitidas; nunca imprime as chaves no terminal.
if (Test-Path '.env') {
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*(SUPABASE_URL|SUPABASE_PUBLISHABLE_KEY|ATLAS_MODEL)\s*=\s*(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2].Trim().Trim('"'), 'Process')
        }
    }
}
& '.\.venv\Scripts\python.exe' -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
