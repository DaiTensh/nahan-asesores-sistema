#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instalador del entorno de desarrollo de Nahan Asesores.

Deja una máquina recién clonada en condiciones de levantar el sistema:
entorno virtual, dependencias, archivo .env, esquema de base de datos y datos
de prueba. Funciona igual en Windows, macOS y Linux, y se puede volver a
ejecutar sin romper nada.

    python scripts/setup.py              # instalación completa
    python scripts/setup.py --solo-bd    # solo importar el esquema y sembrar
    python scripts/setup.py --sin-datos  # sin datos de prueba

Solo usa la biblioteca estándar hasta que termina de instalar dependencias.
"""
import argparse
import getpass
import os
import re
import secrets
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV = os.path.join(RAIZ, ".venv")
ENV = os.path.join(RAIZ, ".env")
EJEMPLO = os.path.join(RAIZ, ".env.example")
ESQUEMA = os.path.join(RAIZ, "database", "nahan_asesores.sql")
SEMILLA = os.path.join(RAIZ, "database", "seed_dev.py")
ES_WINDOWS = os.name == "nt"

VERDE, ROJO, GRIS, FIN = "\033[32m", "\033[31m", "\033[90m", "\033[0m"
if ES_WINDOWS and not os.getenv("WT_SESSION"):
    VERDE = ROJO = GRIS = FIN = ""

paso_n = 0


def paso(texto):
    global paso_n
    paso_n += 1
    print(f"\n[{paso_n}] {texto}")


def bien(texto):
    print(f"    {VERDE}✓{FIN} {texto}")


def aviso(texto):
    print(f"    {GRIS}·{FIN} {texto}")


def morir(texto, arreglo=None):
    print(f"    {ROJO}✗{FIN} {texto}")
    if arreglo:
        print(f"      → {arreglo}")
    sys.exit(1)


def py_venv():
    return os.path.join(VENV, "Scripts" if ES_WINDOWS else "bin", "python.exe" if ES_WINDOWS else "python")


def correr(cmd, **kw):
    return subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, **kw)


# --------------------------------------------------------------------- pasos
def revisar_python():
    paso("Revisando la versión de Python")
    if sys.version_info < (3, 10):
        morir(f"Python {sys.version.split()[0]} es demasiado antiguo.",
              "Instala Python 3.10 o superior desde https://www.python.org/downloads/")
    bien(f"Python {sys.version.split()[0]}")


def crear_venv():
    paso("Preparando el entorno virtual")
    if os.path.isdir(VENV):
        bien(".venv ya existe")
    else:
        r = correr([sys.executable, "-m", "venv", VENV])
        if r.returncode:
            morir("No se pudo crear el entorno virtual.\n" + r.stderr.strip()[:400],
                  "En Debian o Ubuntu puede faltar el paquete: sudo apt install python3-venv")
        bien(".venv creado")
    if not os.path.isfile(py_venv()):
        morir("El entorno virtual quedó incompleto.", f"Borra la carpeta {VENV} y vuelve a ejecutar el instalador.")


def instalar_dependencias():
    paso("Instalando las dependencias")
    correr([py_venv(), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    r = correr([py_venv(), "-m", "pip", "install", "--quiet", "-r",
                os.path.join(RAIZ, "requirements.txt")])
    if r.returncode:
        morir("pip falló:\n" + (r.stderr.strip() or r.stdout.strip())[:600],
              "Revisa tu conexión a internet y vuelve a intentarlo.")
    r = correr([py_venv(), "-m", "pip", "list", "--format=freeze"])
    bien(f"{len(r.stdout.strip().splitlines())} paquetes instalados")


def leer_env():
    if not os.path.isfile(ENV):
        return {}
    d = {}
    for linea in open(ENV, encoding="utf-8"):
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def configurar_env(interactivo=True):
    paso("Configurando el archivo .env")
    actual = leer_env()
    if actual.get("DB_USER") and actual.get("DB_NAME"):
        bien(f".env ya configurado (usuario {actual['DB_USER']}, base {actual['DB_NAME']})")
        return actual

    print("    Datos de tu MySQL local. Enter deja el valor entre corchetes.")
    def pedir(clave, defecto, oculto=False):
        if not interactivo:
            return defecto
        etiqueta = f"      {clave} [{defecto or 'vacío'}]: "
        v = (getpass.getpass(etiqueta) if oculto else input(etiqueta)).strip()
        return v or defecto

    host = pedir("DB_HOST", actual.get("DB_HOST", "127.0.0.1"))
    puerto = pedir("DB_PORT", actual.get("DB_PORT", "3306"))
    usuario = pedir("DB_USER", actual.get("DB_USER", "root"))
    clave = pedir("DB_PASSWORD", actual.get("DB_PASSWORD", ""), oculto=True)
    base = pedir("DB_NAME", actual.get("DB_NAME", "nahan_asesores"))

    plantilla = open(EJEMPLO, encoding="utf-8").read() if os.path.isfile(EJEMPLO) else ""
    valores = {
        "FLASK_ENV": "development", "DEBUG": "true",
        "SECRET_KEY": actual.get("SECRET_KEY") or secrets.token_urlsafe(48),
        "JWT_SECRET": actual.get("JWT_SECRET") or secrets.token_urlsafe(48),
        "DB_HOST": host, "DB_PORT": puerto, "DB_USER": usuario,
        "DB_PASSWORD": clave, "DB_NAME": base,
        "SESSION_COOKIE_SECURE": "false", "SESSION_COOKIE_HTTPONLY": "true",
        "SESSION_COOKIE_SAMESITE": "Lax", "PERMANENT_SESSION_LIFETIME": "480",
        "ALLOWED_ORIGINS": "http://127.0.0.1:5500,http://localhost:5500",
        "TRUST_PROXY": "false", "APP_TIMEZONE": "America/Santiago",
        "FLASK_RUN_HOST": "127.0.0.1", "FLASK_RUN_PORT": "5000",
    }
    lineas, puestas = [], set()
    for linea in plantilla.splitlines():
        m = re.match(r'^([A-Z_]+)=', linea)
        if m and m.group(1) in valores:
            lineas.append(f"{m.group(1)}={valores[m.group(1)]}")
            puestas.add(m.group(1))
        else:
            lineas.append(linea)
    for k, v in valores.items():
        if k not in puestas:
            lineas.append(f"{k}={v}")
    cabecera = ["# Generado por scripts/setup.py — entorno LOCAL de desarrollo.",
                "# Este archivo NO se versiona: está en .gitignore. No lo compartas.", ""]
    open(ENV, "w", encoding="utf-8").write("\n".join(cabecera + lineas).rstrip() + "\n")
    bien(f".env escrito, con SECRET_KEY y JWT_SECRET propios de esta máquina")
    return valores


def conectar(cfg, con_base=False):
    sys.path.insert(0, RAIZ)
    r = correr([py_venv(), "-c", "import mysql.connector"])
    if r.returncode:
        morir("El conector de MySQL no quedó instalado.", "python scripts/setup.py")
    codigo = (
        "import sys, mysql.connector\n"
        "try:\n"
        f"    cn = mysql.connector.connect(host={cfg['DB_HOST']!r}, port={int(cfg['DB_PORT'])},"
        f" user={cfg['DB_USER']!r}, password={cfg['DB_PASSWORD']!r},"
        f"{' database=' + repr(cfg['DB_NAME']) + ',' if con_base else ''} connection_timeout=6)\n"
        "    print('OK', cn.get_server_info())\n"
        "except Exception as e:\n"
        "    print('ERROR', e); sys.exit(1)\n"
    )
    return correr([py_venv(), "-c", codigo])


def importar_esquema(cfg):
    paso("Importando el esquema de la base de datos")
    if not os.path.isfile(ESQUEMA):
        morir(f"No está {ESQUEMA}.")
    r = conectar(cfg)
    if r.returncode:
        morir("MySQL no responde: " + r.stdout.strip().replace("ERROR ", "")[:200],
              "Levanta el servidor MySQL y revisa el usuario y la contraseña en .env.\n"
              "      macOS:   brew services start mysql\n"
              "      Linux:   sudo systemctl start mysql\n"
              "      Windows: inicia el servicio MySQL desde «Servicios»")
    bien("MySQL responde — " + r.stdout.strip().replace("OK ", "servidor "))

    codigo = f'''
import sys, mysql.connector
sql = open({ESQUEMA!r}, encoding="utf-8").read()
cn = mysql.connector.connect(host={cfg['DB_HOST']!r}, port={int(cfg['DB_PORT'])},
                             user={cfg['DB_USER']!r}, password={cfg['DB_PASSWORD']!r})
cur = cn.cursor()
n = 0
for sentencia in [s.strip() for s in sql.split(";") if s.strip()]:
    cur.execute(sentencia)
    while cur.nextset():
        pass
    n += 1
cn.commit(); cur.close(); cn.close()
print("SENTENCIAS", n)
'''
    r = correr([py_venv(), "-c", codigo])
    if r.returncode:
        morir("La importación falló:\n" + (r.stdout + r.stderr).strip()[:600])
    bien(r.stdout.strip().replace("SENTENCIAS ", "") + " sentencias ejecutadas")

    codigo = f'''
import mysql.connector
cn = mysql.connector.connect(host={cfg['DB_HOST']!r}, port={int(cfg['DB_PORT'])},
                             user={cfg['DB_USER']!r}, password={cfg['DB_PASSWORD']!r},
                             database={cfg['DB_NAME']!r})
cur = cn.cursor()
cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s", ({cfg['DB_NAME']!r},))
print("TABLAS", cur.fetchone()[0])
'''
    r = correr([py_venv(), "-c", codigo])
    tablas = int(r.stdout.strip().split()[-1]) if r.returncode == 0 else 0
    if tablas < 19:
        morir(f"La base quedó con {tablas} tablas; se esperaban 19.")
    bien(f"{tablas} tablas creadas en «{cfg['DB_NAME']}»")


def sembrar():
    paso("Cargando los datos de prueba")
    if not os.path.isfile(SEMILLA):
        aviso("No está database/seed_dev.py; se omite.")
        return
    r = correr([py_venv(), SEMILLA])
    if r.returncode:
        morir("La siembra falló:\n" + (r.stdout + r.stderr).strip()[:600])
    for linea in r.stdout.strip().splitlines():
        if linea.strip():
            aviso(linea.strip())


def verificar(cfg):
    paso("Comprobando que el sistema arranca")
    r = correr([py_venv(), "-c",
                "import os; os.chdir(%r);\nfrom backend.app import app\n"
                "c = app.test_client()\n"
                "r = c.get('/')\n"
                "print('HOME', r.status_code)\n"
                "r = c.post('/api/login', json={'email':'renato.villalobos@nahan.local','password':'Nahan.2026'})\n"
                "print('LOGIN', r.status_code)\n" % RAIZ])
    salida = r.stdout.strip()
    if r.returncode or "HOME 200" not in salida:
        morir("La aplicación no arrancó:\n" + (salida + "\n" + r.stderr.strip())[:600])
    bien("La API responde en /")
    if "LOGIN 200" in salida:
        bien("El inicio de sesión funciona con el usuario de prueba")
    else:
        aviso("La API arranca, pero el login de prueba no devolvió 200: " +
              [l for l in salida.splitlines() if l.startswith("LOGIN")][0])


def final():
    activar = r".venv\Scripts\Activate.ps1" if ES_WINDOWS else "source .venv/bin/activate"
    print(f"""
{VERDE}Listo. El entorno quedó instalado.{FIN}

  Levantar el sistema:      python scripts/dev.py
  Abrir en el navegador:    http://127.0.0.1:5500/frontend/auth/login.html
  Usuario de prueba:        renato.villalobos@nahan.local  /  Nahan.2026
  Revisar el entorno:       python scripts/doctor.py

  Para trabajar a mano en esta terminal:  {activar}
""")


def main():
    ap = argparse.ArgumentParser(description="Instala el entorno de desarrollo.")
    ap.add_argument("--solo-bd", action="store_true", help="solo esquema y datos de prueba")
    ap.add_argument("--sin-datos", action="store_true", help="no cargar datos de prueba")
    ap.add_argument("--si-a-todo", action="store_true", help="no preguntar nada; usa los valores por defecto")
    args = ap.parse_args()

    print("Instalador del entorno de desarrollo — Nahan Asesores")
    print(f"Repositorio: {RAIZ}")

    if not args.solo_bd:
        revisar_python()
        crear_venv()
        instalar_dependencias()
    cfg = configurar_env(interactivo=not args.si_a_todo)
    importar_esquema(cfg)
    if not args.sin_datos:
        sembrar()
    verificar(cfg)
    final()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInstalación interrumpida.")
        sys.exit(130)
