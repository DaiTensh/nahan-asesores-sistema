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


def ejecutar(entorno, *argumentos, **extra_entorno):
    base = {clave: valor for clave, valor in os.environ.items() if clave != "NAHAN_SEED_PASSWORD"}
    variables = {**base, "DB_HOST": "127.0.0.1", "DB_PORT": "1", "FLASK_ENV": entorno, **extra_entorno}
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


def test_sin_entorno_definido_tambien_se_niega_porque_se_asume_produccion():
    resultado = ejecutar("")

    assert resultado.returncode == 2 and "(sin definir)" in resultado.stdout
    assert "No hay conexión" not in resultado.stdout


def test_ni_con_el_permiso_expreso_se_siembra_con_la_contrasena_publica():
    resultado = ejecutar("production", "--permitir-produccion")

    assert resultado.returncode == 2 and "NAHAN_SEED_PASSWORD" in resultado.stdout
    assert "No hay conexión" not in resultado.stdout


def test_una_clave_corta_en_produccion_tampoco_se_acepta():
    resultado = ejecutar("production", "--permitir-produccion", NAHAN_SEED_PASSWORD="corta")

    assert resultado.returncode == 2 and "NAHAN_SEED_PASSWORD" in resultado.stdout


def test_con_el_permiso_expreso_y_una_clave_propia_sigue_adelante_hasta_la_conexion():
    resultado = ejecutar("production", "--permitir-produccion", NAHAN_SEED_PASSWORD="Una-clave-propia-1234")

    assert resultado.returncode == 1 and "No hay conexión" in resultado.stdout


def test_en_desarrollo_no_cambia_nada():
    resultado = ejecutar("development")

    assert resultado.returncode == 1 and "No hay conexión" in resultado.stdout
