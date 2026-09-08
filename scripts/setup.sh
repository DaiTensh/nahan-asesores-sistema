#!/usr/bin/env bash
# Instalador para macOS y Linux. Solo busca un Python válido y le pasa el
# trabajo a scripts/setup.py, que es el instalador de verdad y es el mismo
# en los tres sistemas operativos.
set -uo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

MINIMO_MAYOR=3
MINIMO_MENOR=9

# Un entorno virtual activo pone su propio python3 delante de todo. Si ese
# entorno está roto —lo típico tras actualizar Homebrew— parece que no hubiera
# Python en el equipo. Por eso se buscan también las rutas absolutas.
CANDIDATOS=(
  python3.13 python3.12 python3.11 python3.10 python3.9 python3 python
  /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12
  /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3.10 /opt/homebrew/bin/python3
  /usr/local/bin/python3.13 /usr/local/bin/python3.12
  /usr/local/bin/python3.11 /usr/local/bin/python3.10 /usr/local/bin/python3
  /usr/bin/python3
)

INFORME=""
ELEGIDO=""

for c in "${CANDIDATOS[@]}"; do
  ruta="$(command -v "$c" 2>/dev/null)" || continue
  [ -n "$ruta" ] || continue

  version="$("$ruta" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)"

  if [ -z "$version" ]; then
    INFORME+="  $ruta — existe pero no se puede ejecutar (entorno virtual roto o enlace huérfano)"$'\n'
    continue
  fi

  if "$ruta" -c "import sys; sys.exit(0 if sys.version_info >= ($MINIMO_MAYOR,$MINIMO_MENOR) else 1)" 2>/dev/null; then
    ELEGIDO="$ruta"
    break
  fi

  INFORME+="  $ruta — Python $version, anterior al mínimo $MINIMO_MAYOR.$MINIMO_MENOR"$'\n'
done

if [ -n "${VIRTUAL_ENV:-}" ] && [ -n "$ELEGIDO" ]; then
  case "$ELEGIDO" in
    "$VIRTUAL_ENV"/*)
      echo "Aviso: tienes activado el entorno virtual $VIRTUAL_ENV."
      echo "       El instalador va a crear uno nuevo en .venv. Si algo sale raro,"
      echo "       ejecuta 'deactivate' y vuelve a intentarlo."
      echo
      ;;
  esac
fi

if [ -z "$ELEGIDO" ]; then
  echo "No encontré un Python $MINIMO_MAYOR.$MINIMO_MENOR o superior que se pueda ejecutar."
  echo
  if [ -n "$INFORME" ]; then
    echo "Esto es lo que encontré:"
    printf '%s' "$INFORME"
    echo
  else
    echo "No encontré ningún intérprete de Python en el PATH ni en las rutas habituales."
    echo
  fi
  if [ -n "${VIRTUAL_ENV:-}" ]; then
    echo "Tienes un entorno virtual activado ($VIRTUAL_ENV)."
    echo "Prueba primero con:  deactivate  y vuelve a ejecutar este script."
    echo
  fi
  case "$(uname -s)" in
    Darwin) echo "Para instalarlo:  brew install python@3.12" ;;
    Linux)  echo "Para instalarlo:  sudo apt install python3 python3-venv" ;;
  esac
  echo "O descárgalo de https://www.python.org/downloads/"
  echo
  echo "Si crees que sí lo tienes, pega la salida de estos dos comandos:"
  echo "  which -a python3 ; python3 --version"
  exit 1
fi

exec "$ELEGIDO" scripts/setup.py "$@"
