#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ejecuta las pruebas «opt-in» que la suite normal omite, de forma aislada y segura.

* SEC-02 (`tests/test_sec02_mysql_real.py`): levanta un MySQL desechable (puerto efímero, directorio
  temporal) con el mismo ayudante que usan las pruebas de RF60 y lo apaga y borra al terminar.
* RF60 dispositivo separado (`tests/test_rf60_dispositivo_real.py`): en Linux usa /dev/shm; en macOS crea
  una imagen de disco virtual de 512 MB (hdiutil), la monta en una carpeta temporal y la expulsa al
  terminar. No toca discos ni particiones reales.

Uso:  venv/bin/python scripts/pruebas_opt_in.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from tests.mysql_desechable import MySQLDesechable  # noqa: E402


def pytest(archivo, entorno):
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs", archivo],
                          cwd=RAIZ, env={**os.environ, **entorno}).returncode


def main():
    codigos = []
    servidor = MySQLDesechable().iniciar()
    try:
        codigos.append(pytest("tests/test_sec02_mysql_real.py", {"NAHAN_TEST_MYSQL_PORT": str(servidor.puerto)}))
    finally:
        servidor.detener()

    if sys.platform == "darwin" and shutil.which("hdiutil"):
        carpeta = tempfile.mkdtemp(prefix="nahan-vol-")
        imagen, montaje = os.path.join(carpeta, "v.dmg"), os.path.join(carpeta, "m")
        os.mkdir(montaje)
        subprocess.run(["hdiutil", "create", "-size", "512m", "-fs", "Journaled HFS+", "-volname", "NAHANTEST", imagen],
                       check=True, capture_output=True)
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-mountpoint", montaje, imagen], check=True, capture_output=True)
        try:
            codigos.append(pytest("tests/test_rf60_dispositivo_real.py", {"NAHAN_TEST_OTRO_DISPOSITIVO": montaje}))
        finally:
            subprocess.run(["hdiutil", "detach", montaje], capture_output=True)
            shutil.rmtree(carpeta, ignore_errors=True)
    elif os.path.isdir("/dev/shm"):
        codigos.append(pytest("tests/test_rf60_dispositivo_real.py", {}))
    else:
        print("Sin /dev/shm ni hdiutil: las pruebas de dispositivo separado no se pueden ejecutar aquí.")
    sys.exit(1 if any(codigos) else 0)


if __name__ == "__main__":
    main()
