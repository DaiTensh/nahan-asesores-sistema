#!/usr/bin/env bash
# Ejecuta las pruebas en macOS y Linux.  Acepta los argumentos de pytest.
set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"
if [ -x ".venv/bin/python" ]; then exec .venv/bin/python scripts/test.py "$@"; fi
echo "Falta el entorno virtual. Ejecuta primero: bash scripts/setup.sh"
exit 1
