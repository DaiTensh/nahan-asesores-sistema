# Instalador para Windows. Solo busca un Python valido y le pasa el trabajo a
# scripts\setup.py, que es el instalador de verdad y es el mismo en los tres
# sistemas operativos.
#
# Si PowerShell se niega a ejecutarlo, es la politica de ejecucion:
#     powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $raiz

$candidatos = @(
    @("py", @("-3.13")), @("py", @("-3.12")), @("py", @("-3.11")),
    @("py", @("-3.10")), @("py", @("-3.9")), @("py", @("-3")),
    @("python", @()), @("python3", @())
)

$informe = @()
$elegido = $null

foreach ($c in $candidatos) {
    $exe = $c[0]
    $pre = $c[1]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }

    $version = & $exe @pre "-c" "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $version) {
        $informe += "  $exe $($pre -join ' ') - existe pero no se puede ejecutar"
        continue
    }

    & $exe @pre "-c" "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $elegido = $c; break }

    $informe += "  $exe $($pre -join ' ') - Python $version, anterior al minimo 3.9"
}

if ($null -eq $elegido) {
    Write-Host "No encontre un Python 3.9 o superior que se pueda ejecutar."
    Write-Host ""
    if ($informe.Count -gt 0) {
        Write-Host "Esto es lo que encontre:"
        $informe | ForEach-Object { Write-Host $_ }
        Write-Host ""
    }
    Write-Host "Instalalo desde https://www.python.org/downloads/"
    Write-Host "Marca la casilla 'Add Python to PATH' durante la instalacion."
    Write-Host ""
    Write-Host "Si crees que si lo tienes, pega la salida de: where python ; python --version"
    exit 1
}

& $elegido[0] @($elegido[1]) "scripts\setup.py" @args
exit $LASTEXITCODE
