#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico del entorno de desarrollo de Nahan Asesores.

Revisa, en orden, todo lo que hace falta para que el sistema levante, y por
cada cosa que falta dice exactamente qué comando la resuelve.

    bash scripts/doctor.sh               # macOS y Linux
    bash scripts/doctor.sh --json        # el mismo informe en JSON

    powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1  # Windows

Devuelve 0 si el entorno está listo y 1 si falta algo.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(RAIZ, ".env")
ES_WINDOWS = os.name == "nt"
ACTIVAR = r".venv\Scripts\Activate.ps1" if ES_WINDOWS else "source .venv/bin/activate"

# El comando que se le muestra a la persona depende de su sistema: `python`
# a secas no existe en macOS y `python3` no suele existir en Windows.
_PS = "powershell -ExecutionPolicy Bypass -File scripts\\{}.ps1"
CMD_SETUP  = _PS.format("setup")  if ES_WINDOWS else "bash scripts/setup.sh"
CMD_DOCTOR = _PS.format("doctor") if ES_WINDOWS else "bash scripts/doctor.sh"
CMD_DEV    = _PS.format("dev")    if ES_WINDOWS else "bash scripts/dev.sh"
CMD_SEED   = _PS.format("seed")   if ES_WINDOWS else "bash scripts/seed.sh"
CMD_TEST   = _PS.format("test")   if ES_WINDOWS else "bash scripts/test.sh"

CLAVES_ENV = ["DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"]
PAQUETES = [("flask", "Flask"), ("mysql.connector", "mysql-connector-python"),
            ("bcrypt", "bcrypt"), ("dotenv", "python-dotenv"), ("flask_cors", "flask-cors"),
            ("openpyxl", "openpyxl"), ("reportlab", "reportlab")]

resultados = []


def chequeo(nombre, ok, detalle, arreglo=None, critico=True):
    resultados.append({"nombre": nombre, "ok": bool(ok), "detalle": detalle,
                       "arreglo": arreglo, "critico": critico})
    return ok


def puerto_ocupado(puerto):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


# ------------------------------------------------------------------ chequeos
def revisar_python():
    v = sys.version_info
    chequeo("Python 3.9 o superior", v >= (3, 9), f"{v.major}.{v.minor}.{v.micro}",
            "Instala Python 3.9+ desde python.org y vuelve a crear el entorno virtual.")


def revisar_venv():
    en_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    existe = os.path.isdir(os.path.join(RAIZ, ".venv"))
    # «venv/» sin punto es el entorno anterior al instalador. No lo damos por
    # bueno: puede tener dependencias viejas o binarios de otro sistema.
    legado = os.path.isdir(os.path.join(RAIZ, "venv")) and not existe

    if legado:
        detalle = "solo existe el entorno antiguo «venv/», que el instalador ya no usa"
    elif existe:
        detalle = "sí" if en_venv else "existe pero no está activado"
    else:
        detalle = "no existe"

    chequeo("Entorno virtual activado", en_venv and existe, detalle,
            ACTIVAR if (existe and not en_venv) else CMD_SETUP)


def revisar_paquetes():
    faltan = []
    for modulo, paquete in PAQUETES:
        try:
            __import__(modulo)
        except ImportError:
            faltan.append(paquete)
    chequeo("Dependencias de Python", not faltan,
            "todas instaladas" if not faltan else "falta " + ", ".join(faltan),
            CMD_SETUP)


def revisar_pruebas():
    """pytest está en requirements-dev.txt, no en requirements.txt: en el
    servidor no hace falta. Que falte no impide trabajar, pero sí impide
    generar la evidencia de pruebas, así que se avisa sin marcarlo crítico."""
    try:
        __import__("pytest")
    except ImportError:
        chequeo("pytest (para las pruebas)", False, "no está instalado",
                CMD_SETUP, critico=False)
        return
    chequeo("pytest (para las pruebas)", True, f"disponible — se ejecutan con {CMD_TEST}",
            None, critico=False)


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
                CMD_SETUP)
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
                f"{CMD_SETUP} --solo-bd")
        cur.close()
        cn.close()
        return
    cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s", (nombre,))
    tablas = cur.fetchone()[0]
    chequeo("Base de datos", tablas >= 20, f"«{nombre}» con {tablas} tabla(s)",
            f"Reimporta el esquema: {CMD_SETUP} --solo-bd")
    if tablas:
        cur.execute(f"SELECT COUNT(*) FROM `{nombre}`.usuario")
        usuarios = cur.fetchone()[0]
        chequeo("Usuarios para iniciar sesión", usuarios > 0,
                f"{usuarios} usuario(s)", CMD_SEED)
        cur.execute(f"SELECT COUNT(*) FROM `{nombre}`.tarea")
        tareas = cur.fetchone()[0]
        chequeo("Datos de ejemplo", tareas > 0, f"{tareas} tarea(s) cargadas",
                CMD_SEED, critico=False)
    cur.close()
    cn.close()


IDENTIFICACION_API = "API Nahan Asesores funcionando correctamente"


def responde_nuestra_api(puerto):
    """True solo si lo que contesta en el puerto es esta API.

    Que un puerto esté ocupado no prueba que la API esté ahí: en macOS el 5000
    lo toma el receptor de AirPlay. Se compara el mensaje completo, no una
    subcadena, para no dar por buena cualquier respuesta que lo contenga.
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/", timeout=1.5) as r:
            return json.loads(r.read(400).decode("utf-8")).get("message") == IDENTIFICACION_API
    except Exception:
        return False


PUERTOS_API = (5000, 5001, 5002, 5003, 5010)
PUERTOS_FRONT = (5500, 5501, 5502, 5510)


def quien_ocupa(puerto):
    """Nombre del proceso que tiene el puerto, cuando se puede averiguar."""
    if ES_WINDOWS:
        return None
    try:
        r = subprocess.run(["lsof", "-nP", f"-iTCP:{puerto}", "-sTCP:LISTEN"],
                           capture_output=True, text=True, timeout=6)
    except Exception:
        return None
    lineas = [l for l in r.stdout.splitlines()[1:] if l.strip()]
    return lineas[0].split()[0] if lineas else None


def revisar_puertos():
    """No basta con decir «ocupado»: en macOS el 5000 lo toma el receptor de
    AirPlay y el 5500 Live Server, y ninguno de los dos casos es un problema
    mientras quede algún puerto libre, porque dev.py se corre solo. Lo que hay
    que informar es si queda alguno."""
    for candidatos, etiqueta, quien in ((PUERTOS_API, "de la API", "la API"),
                                       (PUERTOS_FRONT, "del frontend", "el frontend")):
        libres = [p for p in candidatos if not puerto_ocupado(p)]
        primero = candidatos[0]
        duenio = quien_ocupa(primero) if puerto_ocupado(primero) else None
        arreglo = None

        corriendo = [p for p in candidatos
                     if p not in libres and responde_nuestra_api(p)]

        if libres and libres[0] == primero:
            detalle = f"{primero} libre para {quien}"
        elif libres:
            detalle = f"{primero} ocupado" + (f" por {duenio}" if duenio else "")
            detalle += f"; dev.py levantará {quien} en el {libres[0]}"
        else:
            detalle = "todos ocupados: " + ", ".join(str(p) for p in candidatos)
            arreglo = ("Cierra lo que los tenga tomados. Para ver qué son: "
                       f"lsof -nP -iTCP:{primero} -sTCP:LISTEN")

        if corriendo:
            detalle += f"; API Nahan detectada en {corriendo[0]} (no se reutiliza)"

        if duenio in ("ControlCe", "ControlCenter", "AirPlayXPCHelper"):
            detalle += f" ({primero}: receptor de AirPlay de macOS)"
            arreglo = arreglo or ("Se puede dejar así. Si prefieres liberar el 5000: "
                                  "Ajustes del Sistema → General → AirDrop y Handoff → "
                                  "Receptor de AirPlay → desactivar")

        chequeo(f"Puertos {etiqueta}", bool(libres), detalle, arreglo, critico=False)


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
    revisar_pruebas()
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
        print(f"  {CMD_DEV}")
    else:
        print(f"Faltan {len(criticos)} cosa(s) por resolver. La forma corta de arreglarlo todo:")
        print(f"  {CMD_SETUP}")
    return 0 if listo else 1


if __name__ == "__main__":
    sys.exit(main())
