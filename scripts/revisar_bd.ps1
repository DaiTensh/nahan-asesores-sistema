# Revisa (y con --limpiar, repara) el rastro de las pruebas en la base. Windows.
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $raiz
$venv = Join-Path $raiz ".venv\Scripts\python.exe"
if (Test-Path $venv) { & $venv "scripts\revisar_bd.py" @args; exit $LASTEXITCODE }
Write-Host "Falta el entorno virtual. Ejecuta primero: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 --solo-deps"
exit 1
