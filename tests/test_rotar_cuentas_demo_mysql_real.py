# -*- coding: utf-8 -*-
"""AUD-012: database/rotar_cuentas_demo.py contra un MySQL real y desechable.

Informa sin cambiar nada, rota solo las cuentas que aceptan la contraseña pública, deja intactas las
cuentas ajenas a la siembra y, en modo desactivar, las pone INACTIVAS. Y la siembra se niega a usar la
contraseña pública fuera de un entorno de desarrollo.
"""
import os
import sys

import pytest

from backend.utils.security import check_password, hash_password
from tests.mysql_desechable import herramientas_disponibles
from tests.test_rut_mysql_real import mundo, servidor  # noqa: F401  (fixtures compartidas)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database"))
import seed_dev  # noqa: E402

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)

PUBLICA = seed_dev.PASSWORD_PUBLICA_DE_DESARROLLO
SCRIPT = "database/rotar_cuentas_demo.py"
AJENA = "persona.real@ejemplo.invalid"


@pytest.fixture
def cuentas(mundo):  # noqa: F811
    hash_publico = hash_password(PUBLICA)
    for nombres, email, rol, area in seed_dev.USUARIOS[:3]:
        mundo.sql("INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) VALUES (1, 3, %s, %s, %s)",
                  (nombres, email, hash_publico))
    # Una cuenta de la siembra que ya cambió su contraseña y una persona real con la misma contraseña pública.
    nombres, email, _r, _a = seed_dev.USUARIOS[3]
    mundo.sql("INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) VALUES (2, 1, %s, %s, %s)",
              (nombres, email, hash_password("Una-clave-propia-1234")))
    mundo.sql("INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) VALUES (2, 1, 'Persona Real', %s, %s)",
              (AJENA, hash_password(PUBLICA)))
    return mundo


def _hashes(mundo):  # noqa: F811
    return {f["email"]: (f["password_hash"], f["estado"]) for f in mundo.consulta("SELECT email, password_hash, estado FROM usuario")}


def test_sin_aplicar_solo_informa_y_no_cambia_nada(cuentas):
    antes = _hashes(cuentas)

    resultado = cuentas.ejecutar(SCRIPT)

    assert resultado.returncode == 1, "sale con 1 mientras haya cuentas activas con la contraseña pública"
    assert "Modo informe" in resultado.stdout and "3 cuenta(s) aceptan la contraseña pública" in resultado.stdout
    assert _hashes(cuentas) == antes


def test_aplicar_rota_solo_las_cuentas_que_aceptan_la_contrasena_publica(cuentas):
    antes = _hashes(cuentas)

    resultado = cuentas.ejecutar(SCRIPT, "--aplicar")

    assert resultado.returncode == 0 and "Rotadas: 3" in resultado.stdout
    despues = _hashes(cuentas)
    for _n, email, _r, _a in seed_dev.USUARIOS[:3]:
        assert not check_password(PUBLICA, despues[email][0]), email
        nueva = next(l.split()[-1] for l in resultado.stdout.splitlines() if l.strip().startswith(email))
        assert check_password(nueva, despues[email][0]), "la contraseña impresa es la que quedó"
    assert despues[seed_dev.USUARIOS[3][1]] == antes[seed_dev.USUARIOS[3][1]], "la que ya tenía clave propia no se toca"
    assert despues[AJENA] == antes[AJENA], "una persona ajena a la siembra nunca se toca"


def test_aplicar_dos_veces_no_vuelve_a_rotar_lo_ya_rotado(cuentas):
    cuentas.ejecutar(SCRIPT, "--aplicar")
    intermedio = _hashes(cuentas)

    segunda = cuentas.ejecutar(SCRIPT, "--aplicar")

    assert "Rotadas: 0" in segunda.stdout and _hashes(cuentas) == intermedio


def test_desactivar_deja_inactivas_las_cuentas_expuestas_sin_imprimir_contrasenas(cuentas):
    resultado = cuentas.ejecutar(SCRIPT, "--aplicar", "--desactivar")

    assert resultado.returncode == 0 and "Desactivadas: 3" in resultado.stdout
    estados = _hashes(cuentas)
    assert {estados[e][1] for _n, e, _r, _a in seed_dev.USUARIOS[:3]} == {"INACTIVO"}
    assert estados[AJENA][1] == "ACTIVO"
    assert "Contraseñas nuevas" not in resultado.stdout


def test_desactivar_sin_aplicar_se_rechaza(cuentas):
    resultado = cuentas.ejecutar(SCRIPT, "--desactivar")

    assert resultado.returncode == 2


def _sembrar(mundo, **extra):  # noqa: F811
    import subprocess
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    entorno = {**os.environ, **mundo.entorno, "FLASK_ENV": "production", "PYTHONDONTWRITEBYTECODE": "1", **extra}
    if "NAHAN_SEED_PASSWORD" not in extra:
        entorno.pop("NAHAN_SEED_PASSWORD", None)
    return subprocess.run([sys.executable, "database/seed_dev.py", "--permitir-produccion"], cwd=raiz, env=entorno,
                          capture_output=True, text=True, timeout=120)


def test_la_siembra_en_produccion_no_usa_la_contrasena_publica(mundo):  # noqa: F811
    sin_clave = _sembrar(mundo)

    assert sin_clave.returncode == 2 and "NAHAN_SEED_PASSWORD" in sin_clave.stdout
    assert not mundo.consulta("SELECT 1 FROM usuario"), "no se creó ninguna cuenta"


def test_la_siembra_en_produccion_con_clave_propia_crea_cuentas_sin_la_contrasena_publica(mundo):  # noqa: F811
    propia = "Clave-solo-para-esta-prueba-9"
    con_clave = _sembrar(mundo, NAHAN_SEED_PASSWORD=propia)

    assert con_clave.returncode == 0, con_clave.stdout + con_clave.stderr
    hash_guardado = mundo.consulta("SELECT password_hash FROM usuario LIMIT 1")[0]["password_hash"]
    assert check_password(propia, hash_guardado) and not check_password(PUBLICA, hash_guardado)
