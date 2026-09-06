#!/usr/bin/env bash
# Instalador para macOS y Linux. Solo busca un Python válido y le pasa el
# trabajo a scripts/setup.py, que es el instalador de verdad y es el mismo
# en los tres sistemas operativos.
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

encontrar_python() {
  for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
        echo "$c"; return 0
      fi
    fi
  done
  return 1
}

if ! PY="$(encontrar_python)"; then
  echo "No encontré Python 3.10 o superior."
  case "$(uname -s)" in
    Darwin) echo "  macOS:  brew install python@3.12" ;;
    Linux)  echo "  Linux:  sudo apt install python3 python3-venv" ;;
  esac
  echo "  O descárgalo de https://www.python.org/downloads/"
  exit 1
fi

exec "$PY" scripts/setup.py "$@"
