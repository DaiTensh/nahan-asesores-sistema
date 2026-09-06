#!/usr/bin/env bash
# Levanta la API y el frontend en macOS y Linux.
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"
if [ -x ".venv/bin/python" ]; then exec .venv/bin/python scripts/dev.py "$@"; fi
exec python3 scripts/dev.py "$@"
