# Levanta la API y el frontend en Windows.
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $raiz
$venv = Join-Path $raiz ".venv\Scripts\python.exe"
if (Test-Path $venv) { & $venv "scripts\dev.py" @args }
else { python "scripts\dev.py" @args }
exit $LASTEXITCODE
