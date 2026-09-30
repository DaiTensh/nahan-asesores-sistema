# -*- coding: utf-8 -*-
"""RF56 — Historiando la Actividad.

GET /api/historial entrega el historial global de AUDITORIA, solo a
administradores, filtrable por módulo, usuario y rango de fechas, y sin
rutas de escritura. También cubre backend/utils/auditoria.py, que es la
interfaz compartida del Incremento 3. Corre sobre SQLite en memoria.
"""
import sqlite3

import pytest

import backend.routes.auth_routes as auth_routes
import backend.routes.historial_routes as historial_routes
import backend.utils.auth as auth_utils
from backend.app import app as flask_app
from backend.utils.auditoria import (
    consultar_auditoria,
    modulo_de_tabla,
    registrar_auditoria,
    tablas_de_modulo,
)

ESQUEMA = """
CREATE TABLE rol (id_rol INTEGER PRIMARY KEY AUTOINCREMENT, nombre_rol TEXT);
CREATE TABLE area (id_area INTEGER PRIMARY KEY AUTOINCREMENT, nombre_area TEXT);
CREATE TABLE usuario (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT, id_rol INTEGER, id_area INTEGER,
    nombres TEXT, email TEXT UNIQUE, password_hash TEXT, estado TEXT DEFAULT 'ACTIVO');
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tabla_afectada TEXT, id_registro INTEGER, accion TEXT, datos_anteriores TEXT,
    datos_nuevos TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_JURIDICA');
INSERT INTO area (nombre_area) VALUES ('ADMINISTRACION'), ('JURIDICA');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) VALUES
 (1, 1, 'Admin Nahan', 'admin@nahan.local', 'hash'),
 (2, 2, 'Usuaria Juridica', 'juridica@nahan.local', 'hash');

INSERT INTO auditoria (id_usuario, tabla_afectada, id_registro, accion, datos_anteriores, datos_nuevos, fecha) VALUES
 (1, 'tarea',   5, 'EDICION',       'id_tarea=5, prioridad=MEDIA', 'id_tarea=5, prioridad=ALTA', '2026-09-01 10:00:00'),
 (2, 'tarea',   5, 'REASIGNACION',  'id_tarea=5, id_responsable=1', 'id_tarea=5, id_responsable=2', '2026-09-10 09:30:00'),
 (1, 'cliente', 3, 'CAMBIO_ESTADO', 'estado: ACTIVO', 'estado: INACTIVO', '2026-09-15 18:00:00'),
 (2, 'documento', 8, 'DESCARGA',    NULL, 'id_documento=8', '2026-09-20 12:00:00');
"""


def _traducir(sql):
    return sql.replace("%s", "?")


class _Cursor:
    def __init__(self, conexion, dictionary):
        self._cursor = conexion.cursor()
        self._dictionary = dictionary
        self.lastrowid = None
        self.rowcount = 0

    def _empaquetar(self, fila):
        if fila is None:
            return None
        return dict(fila) if self._dictionary else tuple(fila)

    def execute(self, sql, params=()):
        self._cursor.execute(_traducir(sql), tuple(params))
        self.lastrowid = self._cursor.lastrowid
        self.rowcount = self._cursor.rowcount

    def fetchone(self):
        return self._empaquetar(self._cursor.fetchone())

    def fetchall(self):
        return [self._empaquetar(fila) for fila in self._cursor.fetchall()]

    def close(self):
        pass


class _Conexion:
    def __init__(self, sqlite_conexion):
        self._conexion = sqlite_conexion

    def cursor(self, dictionary=False):
        return _Cursor(self._conexion, dictionary)

    def commit(self):
        self._conexion.commit()

    def rollback(self):
        self._conexion.rollback()

    def close(self):
        pass


@pytest.fixture
def base():
    from backend.utils.security import hash_password

    conexion = sqlite3.connect(":memory:")
    conexion.row_factory = sqlite3.Row
    conexion.executescript(ESQUEMA)
    conexion.execute("UPDATE usuario SET password_hash = ?", (hash_password("x"),))
    conexion.commit()
    yield conexion
    conexion.close()


@pytest.fixture
def cliente(base, monkeypatch):
    conexion_falsa = lambda: _Conexion(base)

    monkeypatch.setattr(auth_routes, "get_connection", conexion_falsa)
    monkeypatch.setattr(auth_utils, "get_connection", conexion_falsa)
    monkeypatch.setattr(historial_routes, "get_connection", conexion_falsa)
    # RF30 audita el inicio de sesión. Estas pruebas siembran el historial a
    # mano y cuentan sus eventos, así que el login de la prueba no debe
    # agregar uno; el LOGIN real se comprueba en test_rf30_historial_accesos.py.
    monkeypatch.setattr(auth_routes, "registrar_auditoria", lambda *args, **kwargs: None)

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as cliente_http:
        yield cliente_http


def _login(cliente, email):
    respuesta = cliente.post("/api/login", json={"email": email, "password": "x"})
    assert respuesta.status_code == 200


# ---------------------------------------------------------------- interfaz

def test_registrar_auditoria_guarda_el_id_del_registro(base):
    cursor = _Conexion(base).cursor(dictionary=True)

    registrar_auditoria(cursor, 1, "tarea", "EDICION", id_registro=9,
                        datos_anteriores="a", datos_nuevos="b")

    fila = base.execute("SELECT * FROM auditoria WHERE id_registro = 9").fetchone()
    assert (fila["id_usuario"], fila["tabla_afectada"], fila["accion"]) == (1, "tarea", "EDICION")
    assert (fila["datos_anteriores"], fila["datos_nuevos"]) == ("a", "b")


def test_consultar_auditoria_por_registros_y_orden_descendente(base):
    cursor = _Conexion(base).cursor(dictionary=True)

    filas, total = consultar_auditoria(cursor, registros=[("tarea", 5), ("cliente", 3)])

    assert total == 3
    assert [fila["accion"] for fila in filas] == ["CAMBIO_ESTADO", "REASIGNACION", "EDICION"]
    assert filas[0]["modulo"] == "Clientes"
    assert filas[1]["usuario"] == "Usuaria Juridica"


def test_consultar_auditoria_pagina_y_filtra_por_fecha(base):
    cursor = _Conexion(base).cursor(dictionary=True)

    filas, total = consultar_auditoria(cursor, fecha_inicio="2026-09-10", fecha_fin="2026-09-15",
                                       limite=1, offset=1)

    assert total == 2
    assert [fila["accion"] for fila in filas] == ["REASIGNACION"]


def test_modulos_y_tablas():
    assert modulo_de_tabla("tarea") == "Tareas"
    assert modulo_de_tabla("tabla_nueva") == "Otros"
    assert tablas_de_modulo("Clientes") == ["cliente", "observacion_cliente"]


# ---------------------------------------------------------------- endpoint

def test_administrador_ve_el_historial_completo(cliente):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.get("/api/historial")
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["total"] == 4
    assert datos["eventos"][0]["accion"] == "DESCARGA"
    assert {"fecha", "usuario", "modulo", "accion"} <= set(datos["eventos"][0])


def test_usuario_sin_rol_administrador_recibe_403(cliente):
    _login(cliente, "juridica@nahan.local")

    assert cliente.get("/api/historial").status_code == 403
    assert cliente.get("/api/historial/filtros").status_code == 403


def test_sin_sesion_recibe_401(cliente):
    assert cliente.get("/api/historial").status_code == 401


def test_filtra_por_modulo_usuario_y_periodo(cliente):
    _login(cliente, "admin@nahan.local")

    por_modulo = cliente.get("/api/historial?modulo=Tareas").get_json()
    por_usuario = cliente.get("/api/historial?id_usuario=2").get_json()
    por_periodo = cliente.get(
        "/api/historial?fecha_inicio=2026-09-15&fecha_fin=2026-09-30"
    ).get_json()

    assert {e["accion"] for e in por_modulo["eventos"]} == {"EDICION", "REASIGNACION"}
    assert {e["accion"] for e in por_usuario["eventos"]} == {"REASIGNACION", "DESCARGA"}
    assert {e["accion"] for e in por_periodo["eventos"]} == {"CAMBIO_ESTADO", "DESCARGA"}


def test_filtros_invalidos_responden_400(cliente):
    _login(cliente, "admin@nahan.local")

    assert cliente.get("/api/historial?modulo=Inexistente").status_code == 400
    assert cliente.get("/api/historial?id_usuario=abc").status_code == 400
    assert cliente.get(
        "/api/historial?fecha_inicio=2026-09-30&fecha_fin=2026-09-01"
    ).status_code == 400


def test_paginacion(cliente):
    _login(cliente, "admin@nahan.local")

    datos = cliente.get("/api/historial?por_pagina=3&pagina=2").get_json()

    assert (datos["total"], datos["total_paginas"], len(datos["eventos"])) == (4, 2, 1)


def test_el_historial_es_de_solo_lectura(cliente, base):
    _login(cliente, "admin@nahan.local")

    for metodo in ("post", "put", "patch", "delete"):
        assert getattr(cliente, metodo)("/api/historial").status_code == 405

    assert base.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == 4
