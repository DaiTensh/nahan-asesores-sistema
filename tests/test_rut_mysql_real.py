"""RUT contra un MySQL real y desechable: siembra con corrección en su lugar, revisor de solo lectura y registro por API."""
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from backend.utils.validaciones_cliente import validar_rut
from tests.mysql_desechable import (
    BASE_APP, CLAVE_APP, RAIZ, USUARIO_APP, MySQLDesechable, herramientas_disponibles, sembrar_datos_ficticios,
)

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)


@pytest.fixture(scope="module")
def servidor():
    servidor = MySQLDesechable().iniciar()
    yield servidor
    servidor.detener()


@pytest.fixture
def mundo(servidor, monkeypatch):
    root = servidor.conectar()
    cur = root.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {BASE_APP}")
    cur.execute(f"CREATE DATABASE {BASE_APP} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    root.close()
    servidor.cargar_esquema()
    entorno = {"DB_HOST": "127.0.0.1", "DB_PORT": str(servidor.puerto), "DB_USER": USUARIO_APP, "DB_PASSWORD": CLAVE_APP, "DB_NAME": BASE_APP}
    for clave, valor in entorno.items():
        monkeypatch.setenv(clave, valor)

    class Mundo(SimpleNamespace):
        def consulta(self, sql, params=()):
            cn = servidor.conectar(base=BASE_APP)
            cur = cn.cursor(dictionary=True)
            cur.execute(sql, params)
            filas = cur.fetchall()
            cn.close()
            return filas

        def sql(self, sql, params=()):
            cn = servidor.conectar(base=BASE_APP)
            cn.cursor().execute(sql, params)
            cn.commit()
            cn.close()

        def ejecutar(self, *argumentos):
            return subprocess.run([sys.executable, *argumentos], cwd=RAIZ, env={**os.environ, **entorno, "PYTHONDONTWRITEBYTECODE": "1"},
                                  capture_output=True, text=True, timeout=120)
    return Mundo(entorno=entorno)


def test_sembrar_corrige_en_su_lugar_los_rut_antiguos_sin_duplicar_ni_tocar_otros_clientes(mundo):
    mundo.sql("INSERT INTO cliente (rut, razon_social) VALUES ('76.543.210-9', 'Comercial Andes SpA'), "
              "('77.812.455-1', 'Constructora Los Robles Ltda.'), ('12.000.008-K', 'Cliente real de la empresa')")
    antes = {f["razon_social"]: f["id_cliente"] for f in mundo.consulta("SELECT id_cliente, razon_social FROM cliente")}

    primera = mundo.ejecutar("database/seed_dev.py")
    assert primera.returncode == 0, primera.stdout + primera.stderr
    assert "RUT 76.543.210-9 corregido a 11.111.111-1" in primera.stdout

    clientes = mundo.consulta("SELECT id_cliente, rut, razon_social FROM cliente ORDER BY id_cliente")
    assert len(clientes) == 7, "6 de la siembra + el cliente ajeno; ninguno duplicado"
    por_nombre = {c["razon_social"]: c for c in clientes}
    assert por_nombre["Comercial Andes SpA"]["id_cliente"] == antes["Comercial Andes SpA"]
    assert por_nombre["Comercial Andes SpA"]["rut"] == "11.111.111-1"
    assert por_nombre["Constructora Los Robles Ltda."]["id_cliente"] == antes["Constructora Los Robles Ltda."]
    assert por_nombre["Cliente real de la empresa"]["rut"] == "12.000.008-K", "un cliente ajeno a la siembra no se modifica"
    assert all(validar_rut(c["rut"]) == (c["rut"], None) for c in clientes)

    segunda = mundo.ejecutar("database/seed_dev.py")
    assert segunda.returncode == 0 and "corregido" not in segunda.stdout
    assert len(mundo.consulta("SELECT id_cliente FROM cliente")) == 7
    sin_tarea = mundo.consulta("SELECT COUNT(*) AS n FROM tarea t LEFT JOIN cliente c ON c.id_cliente = t.id_cliente WHERE c.id_cliente IS NULL")
    assert sin_tarea[0]["n"] == 0


def test_reset_de_la_siembra_tambien_reconoce_los_rut_antiguos(mundo):
    mundo.sql("INSERT INTO cliente (rut, razon_social) VALUES ('78.220.876-K', 'Importadora del Pacífico SpA'), ('12.000.008-K', 'Ajeno')")
    resultado = mundo.ejecutar("database/seed_dev.py", "--reset")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    ruts = {c["rut"] for c in mundo.consulta("SELECT rut FROM cliente")}
    assert "78.220.876-K" not in ruts and "12.000.008-K" in ruts and "33.333.333-3" in ruts


def test_el_revisor_lista_lo_invalido_y_no_modifica_la_base(mundo):
    mundo.sql("INSERT INTO cliente (rut, razon_social) VALUES ('12.345.678-5', 'Al día'), ('12345678-5', 'Mismo RUT'), "
              "('76.543.210-9', 'Dígito malo'), ('11.111.111-1', 'Correcto')")
    foto = mundo.consulta("SELECT * FROM cliente ORDER BY id_cliente")

    resultado = mundo.ejecutar("database/revisar_ruts.py")

    assert resultado.returncode == 1
    assert "4 cliente(s) revisado(s)" in resultado.stdout and "No se modificó nada" in resultado.stdout
    assert "'76.543.210-9' (Dígito malo): El RUT no es válido" in resultado.stdout
    assert "varios clientes" in resultado.stdout and "11.111.111-1" not in resultado.stdout.replace("#4 '11.111.111-1'", "")
    assert mundo.consulta("SELECT * FROM cliente ORDER BY id_cliente") == foto

    mundo.sql("DELETE FROM cliente WHERE razon_social IN ('Mismo RUT', 'Dígito malo')")
    limpio = mundo.ejecutar("database/revisar_ruts.py")
    assert limpio.returncode == 0 and "Todos los RUT son válidos" in limpio.stdout


def test_el_registro_por_api_aplica_el_digito_verificador_y_evita_duplicados_por_formato(client, iniciar_sesion, mundo, servidor):
    cn = servidor.conectar(base=BASE_APP)
    sembrar_datos_ficticios(cn)
    cn.close()
    iniciar_sesion(usuario_id=1, rol_id=1)

    def registrar(rut, nombre="Cliente de prueba"):
        return client.post("/api/clientes", json={"rut": rut, "razon_social": nombre, "areas": [1]})

    assert registrar("12.345.678-9").status_code == 400
    assert registrar("12.345.678-5").status_code == 201
    assert registrar("123456785", "Mismo RUT sin formato").status_code == 400
    assert registrar("12345678-5", "Mismo RUT con guion").status_code == 400
    assert registrar("12.000.008-k", "Con K minúscula").status_code == 201
    guardados = [c["rut"] for c in mundo.consulta("SELECT rut FROM cliente WHERE razon_social IN ('Cliente de prueba', 'Con K minúscula')")]
    assert sorted(guardados) == ["12.000.008-K", "12.345.678-5"]
