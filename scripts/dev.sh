#!/usr/bin/env bash
# Levanta la API y el frontend en macOS y Linux.
set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python scripts/dev.py "$@"
fi

echo "El entorno virtual no existe todavía."
echo "Ejecuta primero:  bash scripts/setup.sh"
exit 1
