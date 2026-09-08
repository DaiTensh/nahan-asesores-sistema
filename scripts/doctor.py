#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico del entorno de desarrollo de Nahan Asesores.

Revisa, en orden, todo lo que hace falta para que el sistema levante, y por
cada cosa que falta dice exactamente qué comando la resuelve.

    python scripts/doctor.py            # informe legible
    python scripts/doctor.py --json     # el mismo informe en JSON

Devuelve 0 si el entorno está listo y 1 si falta algo.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(RAIZ, ".env")
ES_WINDOWS = os.name == "nt"
ACTIVAR = r".venv\Scripts\Activate.ps1" if ES_WINDOWS else "source .venv/bin/activate"

CLAVES_ENV = ["DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"]
PAQUETES = [("flask", "Flask"), ("mysql.connector", "mysql-connector-python"),
            ("bcrypt", "bcrypt"), ("dotenv", "python-dotenv"), ("flask_cors", "flask-cors")]

resultados = []


def chequeo(nombre, ok, detalle, arreglo=None, critico=True):
    resultados.append({"nombre": nombre, "ok": bool(ok), "detalle": detalle,
                       "arreglo": arreglo, "critico": critico})
    return ok


def puerto_ocupado(puerto):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def puerto_responde_api_propia(puerto):
    """True solo si lo que responde en el puerto es esta API.

    Un puerto ocupado no prueba que la API esté corriendo ahí: en macOS, el
    puerto 5000 lo toma por defecto el Receptor AirPlay (Ajustes del Sistema
    → General → AirDrop y Handoff), y `puerto_ocupado()` daría igual "ocupado"
    en ese caso que si la API estuviera realmente corriendo.
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/", timeout=1) as resp:
            cuerpo = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False
    return cuerpo.get("message") == "API Nahan Asesores funcionando correctamente"


# ------------------------------------------------------------------ chequeos
def revisar_python():
    v = sys.version_info
    chequeo("Python 3.10 o superior", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}",
            "Instala Python 3.10+ desde python.org y vuelve a crear el entorno virtual.")


def revisar_venv():
    en_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    existe = os.path.isdir(os.path.join(RAIZ, ".venv")) or os.path.isdir(os.path.join(RAIZ, "venv"))
    chequeo("Entorno virtual activado", en_venv,
            "sí" if en_venv else ("existe pero no está activado" if existe else "no existe"),
            ACTIVAR if existe else "python scripts/setup.py   (o bash scripts/setup.sh)")


def revisar_paquetes():
    faltan = []
    for modulo, paquete in PAQUETES:
        try:
            __import__(modulo)
        except ImportError:
            faltan.append(paquete)
    chequeo("Dependencias de Python", not faltan,
            "todas instaladas" if not faltan else "falta " + ", ".join(faltan),
            "pip install -r requirements.txt")


def revisar_env():
    if not os.path.isfile(ENV):
        chequeo("Archivo .env", False, "no existe",
                "Copia .env.example a .env, o ejecuta el instalador, que lo genera completo.")
        return False
    contenido = {}
    for linea in open(ENV, encoding="utf-8"):
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            contenido[k.strip()] = v.strip()
    faltan = [k for k in CLAVES_ENV if not contenido.get(k)]
    chequeo("Archivo .env", not faltan,
            "completo" if not faltan else "sin valor en " + ", ".join(faltan),
            "Completa esas claves en .env; DB_PASSWORD puede quedar vacía si tu MySQL local no la pide.")
    return not faltan


def revisar_mysql():
    try:
        sys.path.insert(0, RAIZ)
        from dotenv import load_dotenv
        load_dotenv(ENV)
        import mysql.connector
    except ImportError:
        chequeo("Conexión con MySQL", False, "no se pudo cargar el conector",
                "pip install -r requirements.txt")
        return None
    try:
        cn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", ""), password=os.getenv("DB_PASSWORD", ""),
            connection_timeout=4)
    except Exception as e:
        chequeo("Conexión con MySQL", False, str(e).split("\n")[0][:110],
                "Levanta el servidor MySQL y revisa DB_USER y DB_PASSWORD en .env.")
        return None
    chequeo("Conexión con MySQL", True, f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}")
    return cn


def revisar_base(cn):
    if cn is None:
        return
    nombre = os.getenv("DB_NAME", "nahan_asesores")
    cur = cn.cursor()
    cur.execute("SHOW DATABASES LIKE %s", (nombre,))
    if not cur.fetchone():
        chequeo("Base de datos", False, f"«{nombre}» no existe",
                "python scripts/setup.py --solo-bd")
        cur.close()
        cn.close()
        return
    cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s", (nombre,))
    tablas = cur.fetchone()[0]
    chequeo("Base de datos", tablas >= 19, f"«{nombre}» con {tablas} tabla(s)",
            "Reimporta el esquema: python scripts/setup.py --solo-bd")
    if tablas:
        cur.execute(f"SELECT COUNT(*) FROM `{nombre}`.usuario")
        usuarios = cur.fetchone()[0]
        chequeo("Usuarios para iniciar sesión", usuarios > 0,
                f"{usuarios} usuario(s)", "python database/seed_dev.py")
        cur.execute(f"SELECT COUNT(*) FROM `{nombre}`.tarea")
        tareas = cur.fetchone()[0]
        chequeo("Datos de ejemplo", tareas > 0, f"{tareas} tarea(s) cargadas",
                "python database/seed_dev.py", critico=False)
    cur.close()
    cn.close()


def revisar_puertos():
    ocupado_api = puerto_ocupado(5000)
    if not ocupado_api:
        detalle_api = "libre para la API"
    elif puerto_responde_api_propia(5000):
        detalle_api = "ocupado — la API ya está corriendo"
    else:
        detalle_api = ("ocupado, pero no por esta API — en macOS suele ser el Receptor "
                        "AirPlay (Ajustes del Sistema → General → AirDrop y Handoff)")
    chequeo("Puerto 5000", True, detalle_api, None, critico=False)

    ocupado_frontend = puerto_ocupado(5500)
    chequeo("Puerto 5500", True,
            "ocupado — el frontend ya está corriendo" if ocupado_frontend else "libre para el frontend",
            None, critico=False)


def revisar_git():
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=RAIZ,
                           capture_output=True, text=True, timeout=8)
        rama = r.stdout.strip()
        sucio = subprocess.run(["git", "status", "--porcelain"], cwd=RAIZ,
                               capture_output=True, text=True, timeout=8).stdout.strip()
    except FileNotFoundError:
        chequeo("Repositorio git", False, "git no está instalado",
                "Instálalo desde https://git-scm.com/downloads: lo necesitas para commitear tu trabajo.")
        return
    except Exception:
        chequeo("Repositorio git", False, "no se pudo consultar", None, critico=False)
        return
    if r.returncode or not rama:
        # Caso típico de quien descomprimió el ZIP en vez de clonar.
        chequeo("Repositorio git", False, "esta carpeta no es un repositorio git",
                "Clona el proyecto para poder commitear tu trabajo:\n"
                "           git clone https://github.com/DaiTensh/nahan-asesores-sistema.git\n"
                "           Sin commits propios, tu participación no queda acreditada.")
        return
    n = len(sucio.split("\n")) if sucio else 0
    chequeo("Repositorio git", True,
            f"rama {rama}" + (f", {n} archivo(s) sin commitear" if n else ", limpio"),
            "Trabaja en tu propia rama: git checkout -b feature/inc2-<tu-modulo>" if rama == "main" else None,
            critico=False)


# -------------------------------------------------------------------- salida
def main():
    ap = argparse.ArgumentParser(description="Diagnostica el entorno de desarrollo.")
    ap.add_argument("--json", action="store_true", help="salida en JSON")
    args = ap.parse_args()

    revisar_python()
    revisar_venv()
    revisar_paquetes()
    env_ok = revisar_env()
    revisar_base(revisar_mysql() if env_ok else None)
    revisar_puertos()
    revisar_git()

    criticos = [r for r in resultados if r["critico"] and not r["ok"]]
    listo = not criticos

    if args.json:
        print(json.dumps({"listo": listo, "chequeos": resultados}, ensure_ascii=False, indent=2))
        return 0 if listo else 1

    print("\nDiagnóstico del entorno — Nahan Asesores\n")
    for r in resultados:
        marca = "OK  " if r["ok"] else ("FALTA" if r["critico"] else "aviso")
        print(f"  [{marca:^5}] {r['nombre']}: {r['detalle']}")
        if not r["ok"] and r["arreglo"]:
            print(f"           → {r['arreglo']}")
    print()
    if listo:
        print("El entorno está listo. Levanta el sistema con:")
        print("  python scripts/dev.py")
    else:
        print(f"Faltan {len(criticos)} cosa(s) por resolver. La forma corta de arreglarlo todo:")
        print("  python scripts/setup.py")
    return 0 if listo else 1


if __name__ == "__main__":
    sys.exit(main())
