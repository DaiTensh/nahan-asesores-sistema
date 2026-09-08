#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ejecuta las pruebas del proyecto con el Python del entorno virtual.

Existe por la misma razón que dev.py y doctor.py: `python -m pytest` a secas no
funciona en macOS, donde el comando se llama `python3`, y tampoco funciona si el
entorno virtual no está activado. Este script no depende de ninguna de las dos
cosas.

    bash scripts/test.sh                                  # todas las pruebas
    bash scripts/test.sh tests/test_rf26_restablecimiento.py -v
    bash scripts/test.sh -k restablecimiento

    powershell -ExecutionPolicy Bypass -File scripts\test.ps1     # Windows
"""
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ES_WINDOWS = os.name == "nt"
PY = os.path.join(RAIZ, ".venv", "Scripts" if ES_WINDOWS else "bin",
                  "python.exe" if ES_WINDOWS else "python")


def main():
    python = PY if os.path.isfile(PY) else sys.executable
    instalar = (r"powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"
                if ES_WINDOWS else "bash scripts/setup.sh")

    if not os.path.isfile(PY):
        print("Aviso: no encuentro .venv; uso el Python del sistema.\n")

    hay_pytest = subprocess.run([python, "-c", "import pytest"],
                                capture_output=True).returncode == 0
    if not hay_pytest:
        print("pytest no está instalado en el entorno.")
        print(f"\nEjecuta:\n  {instalar}")
        print("\n(pytest vive en requirements-dev.txt: es una dependencia de")
        print(" desarrollo y no se instala en el servidor.)")
        return 1

    # PYTHONPATH para que `from backend...` resuelva sin instalar el proyecto
    # como paquete, igual que hace dev.py.
    entorno = dict(os.environ, PYTHONPATH=RAIZ)
    argumentos = sys.argv[1:] or ["tests"]
    return subprocess.call([python, "-m", "pytest", *argumentos],
                           cwd=RAIZ, env=entorno)


if __name__ == "__main__":
    sys.exit(main())
