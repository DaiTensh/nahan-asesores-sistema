# -*- coding: utf-8 -*-
"""`database/seed_dev.py` crea siete cuentas con una contraseña pública: no debe poder
ejecutarse por descuido contra un entorno de producción.

Las pruebas no necesitan MySQL: la guardia actúa antes de abrir la conexión, así que
se apunta a un puerto cerrado y se distingue el resultado por el código de salida.
"""
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, "database", "seed_dev.py")


def ejecutar(entorno, *argumentos):
    variables = {**os.environ, "DB_HOST": "127.0.0.1", "DB_PORT": "1", "FLASK_ENV": entorno}
    return subprocess.run([sys.executable, SCRIPT, *argumentos], cwd=RAIZ, env=variables,
                          capture_output=True, text=True, timeout=60)


def test_se_niega_a_sembrar_en_produccion():
    resultado = ejecutar("production")

    assert resultado.returncode == 2
    assert "--permitir-produccion" in resultado.stdout
    assert "No hay conexión" not in resultado.stdout, "ni siquiera debe intentar conectarse"


def test_tampoco_acepta_reset_en_produccion_sin_el_permiso_expreso():
    resultado = ejecutar("production", "--reset")

    assert resultado.returncode == 2 and "No hay conexión" not in resultado.stdout


def test_con_el_permiso_expreso_sigue_adelante_hasta_la_conexion():
    resultado = ejecutar("production", "--permitir-produccion")

    assert resultado.returncode == 1 and "No hay conexión" in resultado.stdout


def test_en_desarrollo_no_cambia_nada():
    resultado = ejecutar("development")

    assert resultado.returncode == 1 and "No hay conexión" in resultado.stdout
