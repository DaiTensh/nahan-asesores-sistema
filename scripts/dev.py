#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Levanta el sistema completo para trabajar: la API de Flask y el frontend
estático, negociando ambos puertos al arrancar.

Ninguno de los dos puertos está fijo, y eso es deliberado:

  - El 5000 lo ocupa el receptor de AirPlay en macOS desde Monterey, y no
    devuelve ningún error reconocible: responde 403 a todo.
  - El 5500 lo ocupa Live Server de VS Code si está abierto.

El frontend se entera solo del puerto que le tocó a la API, porque este script
sirve su propio frontend/assets/js/api_config.js con el puerto ya escrito. El
archivo del repositorio no se toca.

    bash scripts/dev.sh                  # macOS y Linux: API + frontend
    bash scripts/dev.sh --api            # solo la API
    bash scripts/dev.sh --sin-navegador

    powershell -ExecutionPolicy Bypass -File scripts\dev.ps1     # Windows
"""
import argparse

import http.server
import json
import os
import socket
import signal
import subprocess
import sys
import threading
import urllib.request
import time
import webbrowser

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ES_WINDOWS = os.name == "nt"
PY = os.path.join(RAIZ, ".venv", "Scripts" if ES_WINDOWS else "bin",
                  "python.exe" if ES_WINDOWS else "python")

PUERTOS_API = (5000, 5001, 5002, 5003, 5010)
PUERTOS_FRONT = (5500, 5501, 5502, 5510)


def ocupado(puerto):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def elegir_puerto(candidatos):
    for puerto in candidatos:
        if not ocupado(puerto):
            return puerto
    return None


IDENTIFICACION_API = "API Nahan Asesores funcionando correctamente"


def es_nuestra_api(puerto):
    """La API responde en / con su mensaje de identificación. Sirve para no
    confundirla con cualquier otro programa que tenga el puerto tomado: en
    macOS el 5000 es del receptor de AirPlay, que responde 403 a todo.

    Se compara el mensaje completo y no una subcadena: un 403 con la palabra
    «Nahan» en el cuerpo bastaría para dar un falso positivo."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/", timeout=2) as r:
            return json.loads(r.read(400).decode("utf-8")).get("message") == IDENTIFICACION_API
    except Exception:
        return False


def quien_ocupa(puerto):
    """Nombre del proceso que tiene tomado el puerto, si se puede averiguar.
    En macOS y Linux se consulta con lsof; en Windows se omite."""
    if ES_WINDOWS:
        return None
    try:
        r = subprocess.run(["lsof", "-nP", f"-iTCP:{puerto}", "-sTCP:LISTEN"],
                           capture_output=True, text=True, timeout=6)
    except Exception:
        return None

    lineas = [l for l in r.stdout.splitlines()[1:] if l.strip()]
    return lineas[0].split()[0] if lineas else None


def valor_del_env(clave):
    """Lee una clave de .env sin python-dotenv: este script corre antes de que
    la aplicación cargue nada, y no queremos depender del paquete para decidir
    en qué puertos levantar."""
    ruta = os.path.join(RAIZ, ".env")
    if not os.path.isfile(ruta):
        return None
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                if linea.strip().startswith(clave + "="):
                    return linea.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def origenes_del_env():
    valor = valor_del_env("ALLOWED_ORIGINS") or ""
    return [o.strip() for o in valor.split(",") if o.strip()]


def url_frontend(puerto_front):
    """La URL que la API pone en el correo de restablecimiento (RF26). Si el
    frontend no quedó en el puerto que dice .env, el enlace del correo llevaría
    a una página que no existe, así que se corrige — pero solo cuando el valor
    de .env es local. Si alguien apuntó a un servidor real, se respeta."""
    actual = valor_del_env("APP_URL_FRONTEND") or ""
    es_local = (not actual) or "127.0.0.1" in actual or "localhost" in actual
    if puerto_front and es_local:
        return f"http://127.0.0.1:{puerto_front}/frontend"
    return None


def origenes_frontend(puerto_front):
    return [f"http://127.0.0.1:{puerto_front}", f"http://localhost:{puerto_front}"]


def api_config_generado(puerto_api):
    """Este archivo lo sirve únicamente este script, así que el origen siempre
    es el frontend de desarrollo: no hace falta la comprobación de origen que
    lleva la versión del repositorio, que existe para distinguir el desarrollo
    local del despliegue detrás de Nginx."""
    return f"""// Generado por scripts/dev.py — el archivo del repositorio no cambia.
// El puerto de la API se decide al arrancar porque el 5000 puede estar tomado
// (en macOS, por el receptor de AirPlay).
(function () {{
  window.API_CONFIG = {{
    API_URL: "http://127.0.0.1:{puerto_api}/api",
    credentials: "include"
  }};
}})();
"""


def servir_frontend(puerto_front, puerto_api):
    """Sirve el proyecto y reemplaza al vuelo api_config.js para que apunte al
    puerto en el que realmente quedó la API."""
    contenido = api_config_generado(puerto_api).encode("utf-8")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=RAIZ, **k)

        def send_head(self):
            ruta = os.path.realpath(self.translate_path(self.path))
            publico = os.path.realpath(os.path.join(RAIZ, "frontend")) + os.sep
            if not ruta.startswith(publico) or not os.path.isfile(ruta):
                self.send_error(404)
                return None
            return super().send_head()

        def do_GET(self):
            if self.path.split("?")[0].endswith("/assets/js/api_config.js"):
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(contenido)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(contenido)
                return
            super().do_GET()

        def log_message(self, *a, **k):
            pass

    return http.server.ThreadingHTTPServer(("127.0.0.1", puerto_front), Handler)


def explicar_puertos_ocupados():
    """Se llama cuando los cinco candidatos de la API están tomados. Es raro, y
    conviene decir qué se probó en vez de dejar un mensaje genérico."""
    print("No hay ningún puerto libre para la API. Probé: "
          + ", ".join(str(p) for p in PUERTOS_API) + ".")
    print()
    for puerto in PUERTOS_API:
        duenio = quien_ocupa(puerto)
        print(f"  {puerto}: {duenio or 'ocupado (no pude identificar el programa)'}")
    print()
    print("En macOS el 5000 es del receptor de AirPlay desde Monterey; se apaga en")
    print("  Ajustes del Sistema → General → AirDrop y Handoff → Receptor de AirPlay")
    print()
    print("Para ver el resto:")
    print("  lsof -nP -iTCP:5001 -sTCP:LISTEN")


def main():
    ap = argparse.ArgumentParser(description="Levanta la API y el frontend.")
    ap.add_argument("--api", action="store_true", help="solo la API")
    ap.add_argument("--sin-navegador", action="store_true", help="no abrir el navegador")
    args = ap.parse_args()

    python = PY if os.path.isfile(PY) else sys.executable
    instalar = (r"powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"
                if ES_WINDOWS else "bash scripts/setup.sh")

    if not os.path.isfile(PY):
        print("Aviso: no encuentro .venv; uso el Python del sistema.\n")

    # Importar la aplicación completa detecta también dependencias de rutas
    # (por ejemplo openpyxl), y comprueba MySQL antes de anunciar el arranque.
    try:
        comprobacion = subprocess.run(
            [python, "-c", "from backend.app import app; "
             "from backend.config.db import get_connection; "
             "c = get_connection(); "
             "assert c is not None, 'No se pudo conectar a MySQL'; c.close()"],
            cwd=RAIZ, env=dict(os.environ, PYTHONPATH=RAIZ),
            capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        print("La comprobación de la API/MySQL no respondió en 15 segundos.")
        print(f"Ejecuta: {instalar}")
        return 1

    if comprobacion.returncode:
        print("No se pudo preparar la API. Revisa las dependencias y MySQL:")
        print(comprobacion.stdout.strip())
        print(comprobacion.stderr.strip())
        print(f"\nEjecuta:\n  {instalar}")
        return 1

    # Cada ejecución necesita su propia API: una API ya abierta puede ser de
    # otro checkout y no admitir el origen dinámico de este frontend por CORS.
    puerto_api = elegir_puerto(PUERTOS_API)

    if puerto_api is None:
        explicar_puertos_ocupados()
        return 1

    if puerto_api != 5000:
        duenio = quien_ocupa(5000)
        print(f"El puerto 5000 está ocupado{f' por {duenio}' if duenio else ''}; "
              f"levanto la API en el {puerto_api}.")
        if duenio in ("ControlCe", "ControlCenter", "AirPlayXPCHelper"):
            print("  (es el receptor de AirPlay de macOS; se apaga en Ajustes del Sistema →")
            print("   General → AirDrop y Handoff → Receptor de AirPlay)")
    print()

    puerto_front = None
    if not args.api:
        puerto_front = elegir_puerto(PUERTOS_FRONT)

        if puerto_front is None:
            print("No hay puerto libre para el frontend. Cierra una instancia de desarrollo.")
            return 1
        else:
            if puerto_front != 5500:
                duenio = quien_ocupa(5500)
                print(f"El puerto 5500 está ocupado{f' por {duenio}' if duenio else ''} "
                      f"(¿Live Server?); sirvo el frontend en el {puerto_front}.")
                print("  Usa la dirección de abajo, no la de Live Server: Live Server")
                print("  entrega el api_config.js del repositorio, que apunta al 5000.")
                print()

    login = f"http://127.0.0.1:{puerto_front}/frontend/auth/login.html" if puerto_front else None

    # El frontend puede quedar en un puerto distinto del que trae .env, así que
    # se le pasa a la API el origen real para que CORS lo acepte. Las variables
    # del entorno ganan sobre .env: load_dotenv() no sobrescribe lo ya definido.
    origenes = origenes_del_env() or ["http://127.0.0.1:5500", "http://localhost:5500"]
    if puerto_front:
        for origen in origenes_frontend(puerto_front):
            if origen not in origenes:
                origenes.append(origen)

    entorno = dict(os.environ,
                   PYTHONPATH=RAIZ,
                   FLASK_RUN_HOST="127.0.0.1",
                   FLASK_RUN_PORT=str(puerto_api),
                   ALLOWED_ORIGINS=",".join(origenes))

    url = url_frontend(puerto_front)
    if url:
        entorno["APP_URL_FRONTEND"] = url
    proceso = None
    servidor = None
    try:
        # Reservar el puerto antes de mostrar la URL; un error de bind debe
        # llegar a la terminal principal, no perderse dentro de un hilo.
        if puerto_front:
            servidor = servir_frontend(puerto_front, puerto_api)
        proceso = subprocess.Popen(
            [python, "-m", "backend.app"], cwd=RAIZ, env=entorno,
            start_new_session=not ES_WINDOWS)
        limite = time.monotonic() + 15
        while not es_nuestra_api(puerto_api):
            if proceso.poll() is not None:
                print(f"La API terminó al arrancar (código {proceso.returncode}).")
                return 1
            if time.monotonic() >= limite:
                print("La API no respondió en 15 segundos. Revisa el error de arranque anterior.")
                return 1
            time.sleep(0.1)

        if proceso.poll() is not None:
            print("La API terminó antes de completar el arranque.")
            return 1
        if servidor:
            threading.Thread(target=servidor.serve_forever, daemon=True).start()
            print(f"Frontend  →  {login} (PID {os.getpid()})")
        print(f"API       →  http://127.0.0.1:{puerto_api}/api (PID {proceso.pid})")
        print(f"Estado    →  http://127.0.0.1:{puerto_api}/")
        print("Usuario   →  renato.villalobos@nahan.local  /  Nahan.2026")
        print("\nListo. Ctrl+C para detener ambos procesos.\n", flush=True)
        if login and not args.sin_navegador:
            webbrowser.open(login)

        codigo = proceso.wait()
        print(f"La API terminó (código {codigo}); se detiene también el frontend.")
        return codigo or 1
    except KeyboardInterrupt:
        print("\nDetenido.")
        return 0
    except OSError as error:
        print(f"No se pudo levantar el sistema: {error}")
        return 1
    finally:
        if servidor:
            servidor.server_close()
        if proceso:
            if not ES_WINDOWS:
                # Incluye al hijo del recargador de Flask, pero nunca toca
                # procesos de otra terminal o checkout.
                try:
                    os.killpg(proceso.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            elif proceso.poll() is None:
                proceso.terminate()
            proceso.wait()


if __name__ == "__main__":
    sys.exit(main())
