#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Levanta el sistema completo para trabajar: la API de Flask en el puerto 5000 y
el frontend estático en el 5500.

El 5500 no es negociable: frontend/assets/js/api_config.js solo apunta a la API
local cuando la página se sirve desde http://127.0.0.1:5500 o localhost:5500.
Desde cualquier otro origen el frontend intenta hablar con «/api» y no encuentra
nada. Es el mismo puerto que usa Live Server de VS Code, así que si prefieres
esa extensión, funciona igual.

    python scripts/dev.py            # API + frontend
    python scripts/dev.py --api      # solo la API
    python scripts/dev.py --sin-navegador
"""
import argparse
import functools
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ES_WINDOWS = os.name == "nt"
PY = os.path.join(RAIZ, ".venv", "Scripts" if ES_WINDOWS else "bin",
                  "python.exe" if ES_WINDOWS else "python")
LOGIN = "http://127.0.0.1:5500/frontend/auth/login.html"


def ocupado(puerto):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def es_esta_api(puerto):
    """True solo si lo que responde en el puerto es esta API.

    Un puerto ocupado no implica que la API ya esté corriendo: en macOS, el
    puerto 5000 lo toma por defecto el Receptor AirPlay (Ajustes del Sistema
    → General → AirDrop y Handoff), así que hay que confirmar la respuesta
    antes de asumir que basta con no hacer nada.
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/", timeout=1) as resp:
            cuerpo = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False
    return cuerpo.get("message") == "API Nahan Asesores funcionando correctamente"


def servir_frontend():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=RAIZ)
    handler.log_message = lambda *a, **k: None
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 5500), handler)
    servidor.serve_forever()


def main():
    ap = argparse.ArgumentParser(description="Levanta la API y el frontend.")
    ap.add_argument("--api", action="store_true", help="solo la API")
    ap.add_argument("--sin-navegador", action="store_true", help="no abrir el navegador")
    args = ap.parse_args()

    python = PY if os.path.isfile(PY) else sys.executable
    if not os.path.isfile(PY):
        print("Aviso: no encuentro .venv; uso el Python del sistema.")
        print("       Si algo falla, ejecuta primero: python scripts/setup.py\n")

    if ocupado(5000):
        if es_esta_api(5000):
            print("El puerto 5000 ya está ocupado: la API parece estar corriendo.")
            return 1
        print("El puerto 5000 está ocupado, pero no por esta API.")
        if not ES_WINDOWS:
            print("En macOS casi siempre es el Receptor AirPlay: Ajustes del Sistema →")
            print("General → AirDrop y Handoff → Receptor AirPlay, desactívalo y reintenta.")
        print("(Alternativa sin tocar el sistema: define FLASK_RUN_PORT en tu .env con otro")
        print(" puerto, pero también hay que cambiar el puerto 5000 hardcodeado en")
        print(" frontend/assets/js/api_config.js para que el frontend lo encuentre.)")
        return 1

    if not args.api:
        if ocupado(5500):
            print("El puerto 5500 ya está ocupado (¿Live Server abierto?). Sigo solo con la API.")
        else:
            threading.Thread(target=servir_frontend, daemon=True).start()
            print(f"Frontend  →  {LOGIN}")

    print("API       →  http://127.0.0.1:5000/api")
    print("Usuario   →  renato.villalobos@nahan.local  /  Nahan.2026")
    print("\nCtrl+C para detener.\n")

    if not args.api and not args.sin_navegador:
        threading.Timer(1.5, lambda: webbrowser.open(LOGIN)).start()

    entorno = dict(os.environ, PYTHONPATH=RAIZ)
    try:
        return subprocess.call([python, "-m", "backend.app"], cwd=RAIZ, env=entorno)
    except KeyboardInterrupt:
        print("\nDetenido.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
