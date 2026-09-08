#!/usr/bin/env bash
# Recarga los datos de prueba en macOS y Linux.  Acepta --reset.
set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"
if [ -x ".venv/bin/python" ]; then exec .venv/bin/python database/seed_dev.py "$@"; fi
echo "Falta el entorno virtual. Ejecuta primero: bash scripts/setup.sh"
exit 1
