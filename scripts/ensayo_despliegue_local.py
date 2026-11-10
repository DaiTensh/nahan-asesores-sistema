#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ensayo local y aislado de actualización y rollback (no toca AWS ni ninguna base real).

Simula el procedimiento de docs/cierre-tecnico/08_GUIA_IMPLEMENTACION.md con datos ficticios:

  1. Versión anterior (por defecto el commit 93ec4e9: 21 tablas) sobre un MySQL desechable, con Gunicorn.
  2. Copia previa con mysqldump (en la primera actualización aún no existe RF60).
  3. Actualización: código actual + `database/migrar.py` (21 → 24 tablas) + Gunicorn.
  4. Comprobaciones de humo (sesión, login, respaldo con RF60, verificación del paquete).
  5. Rollback: se detiene lo nuevo, se restaura la copia previa y se arranca la versión anterior.
  6. Se comprueba que los datos tras el rollback son idénticos a los de antes de actualizar.

Uso:  venv/bin/python scripts/ensayo_despliegue_local.py [--anterior 93ec4e9]
Sale con 0 si todo coincide. Requiere mysqld, mysqldump, git y el venv del proyecto.
"""
import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from backend.utils.security import hash_password  # noqa: E402
from tests.mysql_desechable import BASE_APP, CLAVE_APP, USUARIO_APP, MySQLDesechable, _dividir_sentencias, contenido_de_tablas  # noqa: E402

CLAVE_ADMIN = "clave-ensayo-ficticia"
EMAIL_ADMIN = "admin-ensayo@ejemplo.invalid"
PASOS = []


def paso(texto, ok=True):
    PASOS.append((texto, ok))
    print(("  OK  " if ok else " FALLA ") + texto, flush=True)
    if not ok:
        raise SystemExit(f"Ensayo fallido en: {texto}")


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def exportar_version(rev, destino):
    if rev == "ACTUAL":
        shutil.copytree(RAIZ, destino, ignore=shutil.ignore_patterns(
            "venv", ".venv", ".git", ".env*", "uploads", "__pycache__", "*.pyc", "docs", "evidencias*"))
    else:
        os.makedirs(destino)
        git = subprocess.Popen(["git", "-C", RAIZ, "archive", rev], stdout=subprocess.PIPE)
        subprocess.run(["tar", "-x", "-C", destino], stdin=git.stdout, check=True)
        git.wait()


def cargar_esquema(servidor, archivo):
    texto = open(archivo, encoding="utf-8").read()
    texto = texto[texto.index("USE nahan_asesores;") + len("USE nahan_asesores;"):]
    cn = servidor.conectar(base=BASE_APP)
    cur = cn.cursor()
    for s in _dividir_sentencias(texto):
        cur.execute(s)
    cn.commit()
    cn.close()


def sembrar(servidor):
    cn = servidor.conectar(base=BASE_APP)
    cur = cn.cursor()
    cur.execute("INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) VALUES (1, 3, 'Admin Ensayo', %s, %s)",
                (EMAIL_ADMIN, hash_password(CLAVE_ADMIN)))
    cur.execute("INSERT INTO cliente (rut, razon_social, email) VALUES ('11.111.111-1', 'Cliente Ñandú «Ensayo»', 'c@ejemplo.invalid')")
    cn.commit()
    cn.close()


class App:
    def __init__(self, carpeta, entorno):
        self.carpeta, self.entorno, self.puerto, self.proc = carpeta, entorno, puerto_libre(), None
        self.registro = tempfile.TemporaryFile()

    def iniciar(self):
        env = {**os.environ, **self.entorno, "PYTHONPATH": self.carpeta}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "gunicorn", "--worker-class", "gthread", "--workers", "2", "--threads", "4",
             "--bind", f"127.0.0.1:{self.puerto}", "backend.app:app"],
            cwd=self.carpeta, env=env, stdout=subprocess.DEVNULL, stderr=self.registro)
        limite = time.time() + 30
        while time.time() < limite:
            try:
                self.pedir("GET", "/api/auth/me")
                return
            except urllib.error.HTTPError:
                return
            except OSError:
                if self.proc.poll() is not None:
                    self.registro.seek(0)
                    raise SystemExit("Gunicorn terminó: " + self.registro.read().decode()[-800:])
                time.sleep(0.3)
        raise SystemExit("Gunicorn no respondió")

    def detener(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

    def pedir(self, metodo, ruta, cuerpo=None, jar=None):
        """`jar` es un dict {nombre: valor}: cookies guardadas a mano (el CookieJar estándar descarta las de 127.0.0.1)."""
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        cabeceras = {"Content-Type": "application/json"} if datos else {}
        if jar:
            cabeceras["Cookie"] = "; ".join(f"{k}={v}" for k, v in jar.items())
        req = urllib.request.Request(f"http://127.0.0.1:{self.puerto}{ruta}", data=datos, method=metodo, headers=cabeceras)
        try:
            r = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as e:
            r = e
        with r:
            if jar is not None:
                for valor in r.headers.get_all("Set-Cookie") or []:
                    nombre, _, resto = valor.partition("=")
                    jar[nombre] = resto.split(";")[0]
            return r.status if hasattr(r, "status") else r.code, json.loads(r.read() or b"null")


def humo(app, titulo, con_respaldo=False):
    codigo, _ = app.pedir("GET", "/api/auth/me")
    paso(f"{titulo}: /api/auth/me sin sesión responde 401", codigo == 401)
    jar = {}
    codigo, cuerpo = app.pedir("POST", "/api/login", {"email": EMAIL_ADMIN, "password": CLAVE_ADMIN}, jar)
    paso(f"{titulo}: el administrador inicia sesión", codigo == 200)
    codigo, cuerpo = app.pedir("GET", "/api/auth/me", jar=jar)
    paso(f"{titulo}: la sesión persiste ({codigo} {str(cuerpo)[:80]})", codigo == 200)
    codigo, cuerpo = app.pedir("GET", "/api/clientes/listado", jar=jar)
    paso(f"{titulo}: el listado de clientes responde", codigo == 200 and len(cuerpo["clientes"]) == 1)
    if con_respaldo:
        codigo, cuerpo = app.pedir("POST", "/api/respaldos", jar=jar)
        paso(f"{titulo}: respaldo manual por la API (RF60) → 201", codigo == 201)
        codigo, cuerpo = app.pedir("GET", "/api/respaldos", jar=jar)
        paso(f"{titulo}: el historial lista el respaldo como EXITOSO", codigo == 200 and cuerpo["respaldos"][0]["estado"] == "EXITOSO")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anterior", default="93ec4e9")
    args = ap.parse_args()
    for herramienta in ("mysqld", "mysqldump", "git"):
        if not shutil.which(herramienta):
            raise SystemExit(f"Falta {herramienta}")
    trabajo = tempfile.mkdtemp(prefix="ensayo-nahan-")
    servidor = MySQLDesechable().iniciar()
    apps = []
    try:
        print(f"Carpeta de trabajo: {trabajo} (se borra al terminar)")
        vieja, nueva = os.path.join(trabajo, "anterior"), os.path.join(trabajo, "nueva")
        exportar_version(args.anterior, vieja)
        exportar_version("ACTUAL", nueva)
        paso(f"versiones exportadas (anterior {args.anterior}, actual = árbol de trabajo)")
        root = servidor.conectar()
        cur = root.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS {BASE_APP}")
        cur.execute(f"CREATE DATABASE {BASE_APP} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        root.close()
        cargar_esquema(servidor, os.path.join(vieja, "database", "nahan_asesores.sql"))
        sembrar(servidor)

        def contar():
            cn = servidor.conectar(base=BASE_APP)
            c = cn.cursor()
            c.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s", (BASE_APP,))
            n = c.fetchone()[0]
            cn.close()
            return n

        paso("base anterior con 21 tablas", contar() == 21)
        entorno_base = {
            "FLASK_ENV": "production", "SECRET_KEY": secrets.token_hex(24), "DB_HOST": "127.0.0.1",
            "DB_PORT": str(servidor.puerto), "DB_USER": USUARIO_APP, "DB_PASSWORD": CLAVE_APP, "DB_NAME": BASE_APP,
            "ADJUNTOS_DIR": os.path.join(trabajo, "adjuntos"), "SESSION_COOKIE_SECURE": "false",
        }
        os.makedirs(entorno_base["ADJUNTOS_DIR"])
        a = App(vieja, entorno_base)
        apps.append(a)
        a.iniciar()
        humo(a, "versión anterior")
        cn = servidor.conectar(base=BASE_APP)
        antes = contenido_de_tablas(cn, ("usuario", "cliente", "rol", "area"))
        cn.close()
        a.detener()

        copia = os.path.join(trabajo, "copia_previa.sql")
        with open(copia, "wb") as f:
            subprocess.run([shutil.which("mysqldump"), "--no-defaults", "-h127.0.0.1", f"-P{servidor.puerto}", "-uroot",
                            "--single-transaction", "--set-gtid-purged=OFF", "--routines", "--default-character-set=utf8mb4", BASE_APP], check=True, stdout=f)
        paso("copia previa con mysqldump", os.path.getsize(copia) > 1000)

        entorno_nuevo = {**entorno_base, "DB_USER": "root", "DB_PASSWORD": "",
                         "RESPALDO_DIR": os.path.join(trabajo, "respaldos")}
        env_migrar = {**os.environ, **entorno_nuevo, "PYTHONPATH": nueva}
        migrar = lambda *x: subprocess.run([sys.executable, "database/migrar.py", *x], cwd=nueva, env=env_migrar, capture_output=True, text=True)
        paso("migrar.py --comprobar detecta migraciones pendientes (código 1)", migrar("--comprobar").returncode == 1)
        r = migrar()
        paso("migrar.py aplica las migraciones", r.returncode == 0)
        paso("la base actualizada tiene 24 tablas", contar() == 24)
        paso("migrar.py --comprobar ya no encuentra pendientes (código 0)", migrar("--comprobar").returncode == 0)
        cn = servidor.conectar(base=BASE_APP)
        c = cn.cursor()
        c.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = %s AND table_name = 'registro_tiempo' "
                  "AND column_name IN ('estado_registro','anulado_por','fecha_anulacion','motivo_anulacion')", (BASE_APP,))
        paso("la migración 013 agregó las 4 columnas de anulación", c.fetchone()[0] == 4)
        c.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = %s AND table_name = 'usuario' "
                  "AND column_name IN ('debe_cambiar_password','version_credenciales')", (BASE_APP,))
        paso("la migración 014 agregó las 2 columnas de contraseña temporal", c.fetchone()[0] == 2)
        cn.close()
        paso("migrar.py es idempotente (segunda ejecución sin error)", migrar().returncode == 0)

        entorno_nuevo["DB_USER"], entorno_nuevo["DB_PASSWORD"] = USUARIO_APP, CLAVE_APP
        b = App(nueva, entorno_nuevo)
        apps.append(b)
        b.iniciar()
        humo(b, "versión nueva", con_respaldo=True)
        b.detener()

        # Rollback: se descarta la base actualizada y se restaura la copia previa.
        root = servidor.conectar()
        cur = root.cursor()
        cur.execute(f"DROP DATABASE {BASE_APP}")
        cur.execute(f"CREATE DATABASE {BASE_APP} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        root.close()
        with open(copia, "rb") as f:
            subprocess.run([shutil.which("mysql") or "mysql", "--no-defaults", "-h127.0.0.1", f"-P{servidor.puerto}", "-uroot",
                            "--default-character-set=utf8mb4", BASE_APP], check=True, stdin=f)
        paso("rollback: copia previa restaurada (21 tablas)", contar() == 21)
        cn = servidor.conectar(base=BASE_APP)
        despues = contenido_de_tablas(cn, ("usuario", "cliente", "rol", "area"))
        cn.close()
        paso("rollback: los datos son idénticos a los de antes de actualizar", despues == antes)
        a2 = App(vieja, {**entorno_base})
        apps.append(a2)
        a2.iniciar()
        humo(a2, "versión anterior tras rollback")
        a2.detener()
        print(f"\nENSAYO COMPLETO: {len(PASOS)} comprobaciones, todas correctas.")
    finally:
        for x in apps:
            x.detener()
        servidor.detener()
        shutil.rmtree(trabajo, ignore_errors=True)


if __name__ == "__main__":
    main()
