#!/usr/bin/env bash
# Diagnóstico del entorno en macOS y Linux.
# Usa el intérprete del entorno virtual si ya existe; si no, busca uno del
# sistema, incluyendo rutas absolutas por si un venv activo lo está tapando.
set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python scripts/doctor.py "$@"
fi

for c in python3.13 python3.12 python3.11 python3.10 python3.9 python3 python \
         /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  ruta="$(command -v "$c" 2>/dev/null)" || continue
  [ -n "$ruta" ] || continue
  if "$ruta" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then
    exec "$ruta" scripts/doctor.py "$@"
  fi
done

echo "No encontré un Python 3.9 o superior que se pueda ejecutar."
echo "  macOS:  brew install python@3.12"
echo "  Linux:  sudo apt install python3"
echo
echo "Pega la salida de:  which -a python3 ; python3 --version"
exit 1
