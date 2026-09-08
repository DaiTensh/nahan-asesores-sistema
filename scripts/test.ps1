# Ejecuta las pruebas en Windows.  Acepta los argumentos de pytest.
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $raiz
$venv = Join-Path $raiz ".venv\Scripts\python.exe"
if (Test-Path $venv) { & $venv "scripts\test.py" @args; exit $LASTEXITCODE }
Write-Host "Falta el entorno virtual. Ejecuta primero: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"
exit 1
