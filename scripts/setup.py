#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instalador del entorno de desarrollo de Nahan Asesores.

Deja una máquina recién clonada en condiciones de levantar el sistema:
entorno virtual, dependencias, archivo .env, esquema de base de datos y datos
de prueba. Funciona igual en Windows, macOS y Linux, y se puede volver a
ejecutar sin romper nada.

    bash scripts/setup.sh                # macOS y Linux: instalación completa
    bash scripts/setup.sh --solo-bd      # solo importar el esquema y sembrar
    bash scripts/setup.sh --sin-datos    # sin datos de prueba

    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # Windows

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
    if sys.version_info < (3, 9):
        morir(f"Python {sys.version.split()[0]} es demasiado antiguo.",
              "Instala Python 3.9 o superior desde https://www.python.org/downloads/")
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
    # Las dependencias de desarrollo van aparte para que el servidor no las
    # instale, pero aquí sí hacen falta: sin pytest no se pueden ejecutar las
    # pruebas, que es parte de la evidencia que pide el ramo.
    dev = os.path.join(RAIZ, "requirements-dev.txt")
    if os.path.isfile(dev):
        r_dev = correr([py_venv(), "-m", "pip", "install", "--quiet", "-r", dev])
        if r_dev.returncode:
            aviso("No se pudieron instalar las dependencias de desarrollo "
                  "(pytest); el sistema funciona igual, pero no vas a poder "
                  "ejecutar las pruebas.")

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


def valores_por_defecto(actual):
    """Todo lo que el sistema espera encontrar en .env, con su valor por defecto.

    Lo que ya esté definido se conserva; lo que falte se completa. Los secretos
    solo se generan la primera vez, para no invalidar las sesiones abiertas ni
    los enlaces de restablecimiento vigentes cada vez que se corre el instalador.
    """
    return {
        "FLASK_ENV": actual.get("FLASK_ENV", "development"),
        "DEBUG": actual.get("DEBUG", "true"),
        "SECRET_KEY": actual.get("SECRET_KEY") or secrets.token_urlsafe(48),
        "JWT_SECRET": actual.get("JWT_SECRET") or secrets.token_urlsafe(48),
        "DB_HOST": actual.get("DB_HOST", "127.0.0.1"),
        "DB_PORT": actual.get("DB_PORT") or "3306",
        "DB_USER": actual.get("DB_USER", "root"),
        "DB_PASSWORD": actual.get("DB_PASSWORD", ""),
        "DB_NAME": actual.get("DB_NAME", "nahan_asesores"),
        "SESSION_COOKIE_SECURE": actual.get("SESSION_COOKIE_SECURE", "false"),
        "SESSION_COOKIE_HTTPONLY": actual.get("SESSION_COOKIE_HTTPONLY", "true"),
        "SESSION_COOKIE_SAMESITE": actual.get("SESSION_COOKIE_SAMESITE", "Lax"),
        "PERMANENT_SESSION_LIFETIME": actual.get("PERMANENT_SESSION_LIFETIME", "480"),
        "ALLOWED_ORIGINS": actual.get("ALLOWED_ORIGINS")
                           or "http://127.0.0.1:5500,http://localhost:5500",
        "TRUST_PROXY": actual.get("TRUST_PROXY", "false"),
        "APP_TIMEZONE": actual.get("APP_TIMEZONE", "America/Santiago"),
        "FLASK_RUN_HOST": actual.get("FLASK_RUN_HOST", "127.0.0.1"),
        "FLASK_RUN_PORT": actual.get("FLASK_RUN_PORT") or "5000",
        "SMTP_HOST": actual.get("SMTP_HOST", ""),
        "SMTP_PORT": actual.get("SMTP_PORT") or "587",
        "SMTP_USER": actual.get("SMTP_USER", ""),
        "SMTP_PASSWORD": actual.get("SMTP_PASSWORD", ""),
        "SMTP_FROM": actual.get("SMTP_FROM", ""),
        "SMTP_FROM_NAME": actual.get("SMTP_FROM_NAME") or "Nahan Asesores",
        "APP_URL_FRONTEND": actual.get("APP_URL_FRONTEND")
                            or "http://127.0.0.1:5500/frontend",
        "RESET_TOKEN_MINUTOS": actual.get("RESET_TOKEN_MINUTOS") or "60",
    }


def escribir_env(valores):
    plantilla = open(EJEMPLO, encoding="utf-8").read() if os.path.isfile(EJEMPLO) else ""
    lineas, puestas = [], set()

    for linea in plantilla.splitlines():
        m = re.match(r'^([A-Z_]+)=', linea)
        if m and m.group(1) in valores:
            lineas.append(f"{m.group(1)}={valores[m.group(1)]}")
            puestas.add(m.group(1))
        else:
            lineas.append(linea)

    for clave, valor in valores.items():
        if clave not in puestas:
            lineas.append(f"{clave}={valor}")

    cabecera = ["# Generado por scripts/setup.py — entorno LOCAL de desarrollo.",
                "# Este archivo NO se versiona: está en .gitignore. No lo compartas.", ""]
    open(ENV, "w", encoding="utf-8").write("\n".join(cabecera + lineas).rstrip() + "\n")


def configurar_env(interactivo=True):
    paso("Configurando el archivo .env")
    actual = leer_env()
    ya_estaba = bool(actual.get("DB_USER") and actual.get("DB_NAME"))

    if ya_estaba:
        # El archivo puede venir de una versión anterior del proyecto y no traer
        # todas las claves. Se completa sin preguntar nada ni tocar lo existente.
        valores = valores_por_defecto(actual)
        faltaban = sorted(k for k in valores if k not in actual)

        bien(f".env ya configurado (usuario {valores['DB_USER']}, base {valores['DB_NAME']})")

        if faltaban:
            escribir_env(valores)
            aviso(f"Se completaron {len(faltaban)} clave(s) que faltaban: "
                  + ", ".join(faltaban[:6]) + ("…" if len(faltaban) > 6 else ""))
        return valores

    print("    Datos de tu MySQL local. Enter deja el valor entre corchetes.")

    def pedir(clave, defecto, oculto=False):
        if not interactivo:
            return defecto
        etiqueta = f"      {clave} [{defecto or 'vacío'}]: "
        v = (getpass.getpass(etiqueta) if oculto else input(etiqueta)).strip()
        return v or defecto

    preguntado = dict(actual)
    preguntado["DB_HOST"] = pedir("DB_HOST", actual.get("DB_HOST", "127.0.0.1"))
    preguntado["DB_PORT"] = pedir("DB_PORT", actual.get("DB_PORT", "3306"))
    preguntado["DB_USER"] = pedir("DB_USER", actual.get("DB_USER", "root"))
    preguntado["DB_PASSWORD"] = pedir("DB_PASSWORD", actual.get("DB_PASSWORD", ""), oculto=True)
    preguntado["DB_NAME"] = pedir("DB_NAME", actual.get("DB_NAME", "nahan_asesores"))

    valores = valores_por_defecto(preguntado)
    escribir_env(valores)
    bien(".env escrito, con SECRET_KEY y JWT_SECRET propios de esta máquina")
    return valores


def exigir_entorno():
    """Los pasos de base de datos corren con el intérprete del entorno virtual.
    Con --solo-bd es posible llegar aquí sin haberlo creado."""
    if not os.path.isfile(py_venv()):
        morir("El entorno virtual no existe todavía.",
              "Ejecuta el instalador completo antes de usar --solo-bd:\n      "
              + (r"powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"
                 if ES_WINDOWS else "bash scripts/setup.sh"))


def conectar(cfg, con_base=False):
    exigir_entorno()
    sys.path.insert(0, RAIZ)
    r = correr([py_venv(), "-c", "import mysql.connector"])
    if r.returncode:
        morir("El conector de MySQL no quedó instalado.",
              r"powershell -ExecutionPolicy Bypass -File scripts\setup.ps1" if ES_WINDOWS
              else "bash scripts/setup.sh")
    codigo = (
        "import sys, mysql.connector\n"
        "try:\n"
        f"    cn = mysql.connector.connect(host={cfg.get('DB_HOST', '127.0.0.1')!r},"
        f" port={int(cfg.get('DB_PORT') or 3306)},"
        f" user={cfg['DB_USER']!r}, password={cfg['DB_PASSWORD']!r},"
        f"{' database=' + repr(cfg['DB_NAME']) + ',' if con_base else ''} connection_timeout=6)\n"
        "    print('OK', cn.get_server_info())\n"
        "except Exception as e:\n"
        "    print('ERROR', e); sys.exit(1)\n"
    )
    return correr([py_venv(), "-c", codigo])


def contenido_de_la_base(cfg):
    """(usuarios, tareas) si la base ya existe; None si no existe o no se pudo
    consultar. Sirve para no borrar sin avisar el trabajo de quien vuelve a
    correr el instalador: el esquema empieza con DROP DATABASE."""
    codigo = f"""
import mysql.connector
cn = mysql.connector.connect(host={cfg['DB_HOST']!r}, port={int(cfg['DB_PORT'])},
                             user={cfg['DB_USER']!r}, password={cfg['DB_PASSWORD']!r},
                             database={cfg['DB_NAME']!r})
cur = cn.cursor()
cur.execute("SELECT COUNT(*) FROM usuario")
u = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM tarea")
print("CONTENIDO", u, cur.fetchone()[0])
"""
    r = correr([py_venv(), "-c", codigo])
    if r.returncode or "CONTENIDO" not in r.stdout:
        return None
    partes = r.stdout.strip().split()
    return int(partes[-2]), int(partes[-1])


def confirmar_borrado(cfg, interactivo):
    datos = contenido_de_la_base(cfg)
    if not datos or datos == (0, 0):
        return
    usuarios, tareas = datos

    aviso(f"La base «{cfg['DB_NAME']}» ya existe: {usuarios} usuario(s) y {tareas} tarea(s).")
    aviso("El esquema empieza con DROP DATABASE, así que se borra y se vuelve a crear.")

    if not interactivo:
        aviso("--si-a-todo: se continúa y se pierde el contenido actual.")
        return

    respuesta = input("      ¿Continuar y perder ese contenido? [s/N]: ").strip().lower()
    if respuesta not in ("s", "si", "sí", "y", "yes"):
        print("\n    Cancelado. La base quedó intacta.")
        print("    Si solo querías instalar dependencias:")
        print("      " + (r"powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 --solo-deps"
                          if ES_WINDOWS else "bash scripts/setup.sh --solo-deps"))
        sys.exit(0)


def importar_esquema(cfg, interactivo=True):
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

    confirmar_borrado(cfg, interactivo)

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
    if tablas < 20:
        morir(f"La base quedó con {tablas} tablas; se esperaban 20.")
    bien(f"{tablas} tablas creadas en «{cfg['DB_NAME']}»")


def sembrar():
    paso("Cargando los datos de prueba")
    if not os.path.isfile(SEMILLA):
        aviso("No está database/seed_dev.py; se omite.")
        return

    exigir_entorno()
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
    # Cada sistema recibe su propio comando: `python` a secas no existe en macOS.
    envoltorio = (lambda n: rf"powershell -ExecutionPolicy Bypass -File scripts\{n}.ps1") if ES_WINDOWS \
        else (lambda n: f"bash scripts/{n}.sh")
    print(f"""
{VERDE}Listo. El entorno quedó instalado.{FIN}

  Levantar el sistema:      {envoltorio("dev")}
  El navegador se abre solo; el script imprime la dirección exacta.
  Usuario de prueba:        renato.villalobos@nahan.local  /  Nahan.2026
  Revisar el entorno:       {envoltorio("doctor")}
  Ejecutar las pruebas:     {envoltorio("test")}
  Recargar datos de prueba: {envoltorio("seed")} --reset

  Para trabajar a mano en esta terminal:  {activar}
""")


def main():
    ap = argparse.ArgumentParser(description="Instala el entorno de desarrollo.")
    ap.add_argument("--solo-bd", action="store_true", help="solo esquema y datos de prueba")
    ap.add_argument("--solo-deps", action="store_true",
                    help="solo dependencias; no toca .env ni la base de datos")
    ap.add_argument("--sin-datos", action="store_true", help="no cargar datos de prueba")
    ap.add_argument("--si-a-todo", action="store_true", help="no preguntar nada; usa los valores por defecto")
    args = ap.parse_args()

    print("Instalador del entorno de desarrollo — Nahan Asesores")
    print(f"Repositorio: {RAIZ}")

    if not args.solo_bd:
        revisar_python()
        crear_venv()
        instalar_dependencias()

    # --solo-deps existe para el caso de agregar una dependencia nueva a un
    # entorno que ya funciona: volver a correr el instalador completo importaría
    # el esquema, y el esquema empieza con DROP DATABASE.
    if args.solo_deps:
        print("\n    Dependencias al día. No se tocó .env ni la base de datos.")
        return 0

    cfg = configurar_env(interactivo=not args.si_a_todo)
    importar_esquema(cfg, interactivo=not args.si_a_todo)
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
