# Diagnostico del entorno en Windows.
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $raiz
$venv = Join-Path $raiz ".venv\Scripts\python.exe"
if (Test-Path $venv) { & $venv "scripts\doctor.py" @args; exit $LASTEXITCODE }
foreach ($c in @("python", "py", "python3")) {
    if (Get-Command $c -ErrorAction SilentlyContinue) { & $c "scripts\doctor.py" @args; exit $LASTEXITCODE }
}
Write-Host "No encontre Python en este equipo."
Write-Host "  Instalalo desde https://www.python.org/downloads/ y marca 'Add Python to PATH'."
exit 1
