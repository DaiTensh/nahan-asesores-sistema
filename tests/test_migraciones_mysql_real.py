"""Migraciones 001–012 contra un MySQL real y desechable.

Comprueba que una instalación limpia (database/nahan_asesores.sql) y la
actualización de una instalación anterior (el esquema entregado en v1.0.0 más
las migraciones pendientes, aplicadas con database/migrar.py) lleguen a la misma
estructura, sin perder los datos existentes. Se omite si no hay mysqld o si el
repositorio no conserva la etiqueta v1.0.0.
"""
import importlib.util
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tests.mysql_desechable import (
    ESQUEMA, RAIZ, MySQLDesechable, _dividir_sentencias, herramientas_disponibles,
)

ETIQUETA_BASE = "v1.0.0"


def _esquema_de_la_etiqueta():
    try:
        return subprocess.run(["git", "show", f"{ETIQUETA_BASE}:database/nahan_asesores.sql"], cwd=RAIZ,
                              capture_output=True, text=True, check=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None


pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or _esquema_de_la_etiqueta() is None or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld/mysqldump y la etiqueta v1.0.0 en el repositorio",
)


def _cargar(cn, texto):
    texto = texto[texto.index("USE nahan_asesores;") + len("USE nahan_asesores;"):]
    cur = cn.cursor()
    for sentencia in _dividir_sentencias(texto):
        cur.execute(sentencia)
    cn.commit()


def _migrar():
    especificacion = importlib.util.spec_from_file_location("migrar_real", os.path.join(RAIZ, "database", "migrar.py"))
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def _estructura(cn, base):
    cur = cn.cursor()
    resultado = {}
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s ORDER BY 1", (base,))
    resultado["tablas"] = [f[0] for f in cur.fetchall()]
    cur.execute(
        "SELECT table_name, column_name, column_type, is_nullable, column_default, extra, collation_name "
        "FROM information_schema.columns WHERE table_schema = %s ORDER BY table_name, column_name", (base,))
    resultado["columnas"] = cur.fetchall()
    cur.execute(
        "SELECT table_name, index_name, non_unique, seq_in_index, column_name FROM information_schema.statistics "
        "WHERE table_schema = %s ORDER BY table_name, index_name, seq_in_index", (base,))
    resultado["indices"] = cur.fetchall()
    cur.execute(
        "SELECT k.table_name, k.constraint_name, k.column_name, k.referenced_table_name, k.referenced_column_name, "
        "r.delete_rule, r.update_rule FROM information_schema.key_column_usage k "
        "JOIN information_schema.referential_constraints r ON r.constraint_schema = k.table_schema "
        "AND r.constraint_name = k.constraint_name AND r.table_name = k.table_name "
        "WHERE k.table_schema = %s ORDER BY 1, 2, k.ordinal_position", (base,))
    resultado["claves_foraneas"] = cur.fetchall()
    cur.execute("SELECT nombre_parametro, valor_parametro, tipo_dato FROM parametros_sistema ORDER BY 1")
    resultado["parametros"] = cur.fetchall()
    cur.execute("SELECT nombre_rol FROM rol ORDER BY 1")
    resultado["roles"] = cur.fetchall()
    return resultado


@pytest.fixture(scope="module")
def entorno():
    servidor = MySQLDesechable().iniciar()
    root = servidor.conectar()
    cur = root.cursor()
    for base in ("inst_limpia", "inst_actualizada"):
        cur.execute(f"CREATE DATABASE {base} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    root.close()

    limpia = servidor.conectar(base="inst_limpia")
    with open(ESQUEMA, encoding="utf-8") as archivo:
        _cargar(limpia, archivo.read())

    anterior = servidor.conectar(base="inst_actualizada")
    _cargar(anterior, _esquema_de_la_etiqueta())
    cur = anterior.cursor()
    # Datos ficticios que la actualización no debe perder.
    cur.execute("INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) VALUES (1, 3, 'Admin Ficticia', 'a@ejemplo.invalid', 'h')")
    cur.execute("INSERT INTO cliente (rut, razon_social) VALUES ('11.111.111-1', 'Cliente Ficticio')")
    cur.execute("INSERT INTO auditoria (id_usuario, tabla_afectada, accion) VALUES (1, 'cliente', 'CLIENTE_CREADO')")
    cur.execute("INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado) VALUES "
                "(1, 3, 1, 1, 'Tarea anterior', 'EN_PROCESO'), (1, 3, 1, 1, 'Tarea cerrada', 'COMPLETADA')")
    cur.execute("INSERT INTO registro_tiempo (id_usuario, id_cliente, id_tarea, fecha, hora_inicio, hora_fin, "
                "duracion_minutos, tarifa_hora) VALUES (1, 1, 1, '2026-10-01', '09:00:00', '10:00:00', 60, 30000)")
    anterior.commit()
    yield SimpleNamespace(servidor=servidor, limpia=limpia, anterior=anterior)
    limpia.close()
    anterior.close()
    servidor.detener()



def test_la_instalacion_limpia_reconoce_todas_las_migraciones_como_aplicadas(entorno):
    migrar = _migrar()
    cur = entorno.limpia.cursor()
    assert [n for n, _, _ in migrar.migraciones()] == ["001", "002", "003", "004", "005", "006", "007", "008", "009", "010", "011", "012"]
    assert migrar.pendientes(cur) == []


def test_una_instalacion_de_v1_0_0_tiene_pendientes_exactamente_las_migraciones_nuevas(entorno):
    migrar = _migrar()
    assert migrar.pendientes(entorno.anterior.cursor()) == ["008", "009", "010", "011", "012"]


def test_actualizar_aplica_las_pendientes_sin_perder_datos_y_en_orden(entorno):
    migrar = _migrar()
    cur = entorno.anterior.cursor()
    for numero, nombre, ruta in migrar.migraciones():
        if migrar.aplicada(cur, numero):
            continue
        assert migrar.aplicar(entorno.anterior, ruta) == 0, nombre
        assert migrar.aplicada(cur, numero) is True, nombre
    assert migrar.pendientes(cur) == []

    cur.execute("SELECT nombres FROM usuario")
    assert cur.fetchall() == [("Admin Ficticia",)]
    cur.execute("SELECT razon_social FROM cliente")
    assert cur.fetchall() == [("Cliente Ficticio",)]
    cur.execute("SELECT accion FROM auditoria")
    assert cur.fetchall() == [("CLIENTE_CREADO",)]
    cur.execute("SELECT titulo, estado FROM tarea ORDER BY id_tarea")
    assert cur.fetchall() == [("Tarea anterior", "EN_PROCESO"), ("Tarea cerrada", "COMPLETADA")], \
        "ampliar el ENUM de estado no altera las tareas existentes"
    cur.execute("SELECT origen, observacion, monto FROM registro_tiempo")
    assert cur.fetchall() == [("TEMPORIZADOR", None, 30000)], \
        "los registros de tiempo anteriores quedan como del temporizador y conservan su monto"


def test_actualizar_y_instalar_desde_cero_llegan_a_la_misma_estructura(entorno):
    test_actualizar_aplica_las_pendientes_sin_perder_datos_y_en_orden(entorno)
    limpia = _estructura(entorno.limpia, "inst_limpia")
    actualizada = _estructura(entorno.anterior, "inst_actualizada")
    for parte in limpia:
        assert limpia[parte] == actualizada[parte], f"difiere: {parte}"
    assert len(limpia["tablas"]) == 24, "21 de v1.0.0 + cliente_reciente + intento_login_fallido + respaldo"


def test_aplicar_dos_veces_es_inofensivo(entorno):
    test_actualizar_aplica_las_pendientes_sin_perder_datos_y_en_orden(entorno)
    migrar = _migrar()
    for numero, nombre, ruta in migrar.migraciones():
        if numero in ("008", "009", "010", "011", "012"):
            migrar.aplicar(entorno.anterior, ruta)  # no debe lanzar: los «ya existe» se toleran
    assert migrar.pendientes(entorno.anterior.cursor()) == []


def test_el_script_migrar_deja_la_base_al_dia_y_comprueba_sin_modificar(entorno):
    test_actualizar_aplica_las_pendientes_sin_perder_datos_y_en_orden(entorno)
    env = {**os.environ, "DB_HOST": "127.0.0.1", "DB_PORT": str(entorno.servidor.puerto), "DB_USER": "root",
           "DB_PASSWORD": "", "DB_NAME": "inst_actualizada", "PYTHONDONTWRITEBYTECODE": "1"}
    for argumentos in ([], ["--comprobar"]):
        proceso = subprocess.run([sys.executable, os.path.join(RAIZ, "database", "migrar.py"), *argumentos], cwd=RAIZ,
                                 env=env, capture_output=True, text=True, timeout=60)
        assert proceso.returncode == 0, proceso.stdout + proceso.stderr
        assert "al día" in proceso.stdout
        assert "PENDIENTE" not in proceso.stdout
