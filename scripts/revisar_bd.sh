#!/usr/bin/env bash
# Revisa (y con --limpiar, repara) el rastro de las pruebas en la base. macOS y Linux.
set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"
if [ -x ".venv/bin/python" ]; then exec .venv/bin/python scripts/revisar_bd.py "$@"; fi
echo "Falta el entorno virtual. Ejecuta primero: bash scripts/setup.sh --solo-deps"
exit 1
