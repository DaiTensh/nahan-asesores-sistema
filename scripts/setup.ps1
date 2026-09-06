# Instalador para Windows. Solo busca un Python valido y le pasa el trabajo a
# scripts\setup.py, que es el instalador de verdad y es el mismo en los tres
# sistemas operativos.
#
# Si PowerShell se niega a ejecutarlo, es la politica de ejecucion. Abre
# PowerShell y corre esto una vez:
#     Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# O bien, sin cambiar nada:
#     powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $raiz

function Buscar-Python {
    foreach ($c in @("py -3.12", "py -3.11", "py -3.10", "py -3", "python3", "python")) {
        $partes = $c.Split(" ")
        $exe = $partes[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $args = @()
        if ($partes.Count -gt 1) { $args += $partes[1] }
        $args += @("-c", "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)")
        & $exe @args 2>$null
        if ($LASTEXITCODE -eq 0) { return ,@($exe, $partes[1..($partes.Count-1)]) }
    }
    return $null
}

$py = Buscar-Python
if ($null -eq $py) {
    Write-Host "No encontre Python 3.10 o superior."
    Write-Host "  Instalalo desde https://www.python.org/downloads/"
    Write-Host "  Marca la casilla 'Add Python to PATH' durante la instalacion."
    exit 1
}

$exe = $py[0]
$pre = @($py[1] | Where-Object { $_ })
& $exe @pre "scripts\setup.py" @args
exit $LASTEXITCODE
