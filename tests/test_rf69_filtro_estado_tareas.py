# -*- coding: utf-8 -*-
"""RF69 — Filtrando Tareas por Estado.

GET /api/tareas/pendientes?estado=<estado> acota el listado a un estado
exacto (incluidos COMPLETADA y CANCELADA, que el listado por defecto no
muestra) sin reemplazar la restricción de "solo mis tareas" que ya aplica a
quien no es ADMINISTRADOR. Corre sobre SQLite en memoria, igual que los demás
tests de tareas.
"""
import sqlite3

import pytest

import backend.routes.auth_routes as auth_routes
import backend.routes.tareas_routes as tareas_routes
import backend.utils.auth as auth_utils
from backend.app import app as flask_app

ESQUEMA = """
CREATE TABLE rol (id_rol INTEGER PRIMARY KEY AUTOINCREMENT, nombre_rol TEXT);
CREATE TABLE area (id_area INTEGER PRIMARY KEY AUTOINCREMENT, nombre_area TEXT);
CREATE TABLE usuario (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT, id_rol INTEGER, id_area INTEGER,
    nombres TEXT, email TEXT UNIQUE, password_hash TEXT, estado TEXT DEFAULT 'ACTIVO');
CREATE TABLE cliente (id_cliente INTEGER PRIMARY KEY AUTOINCREMENT, razon_social TEXT);
CREATE TABLE tarea (
    id_tarea INTEGER PRIMARY KEY AUTOINCREMENT, id_cliente INTEGER, id_area INTEGER,
    id_responsable INTEGER, id_creador INTEGER, titulo TEXT, descripcion TEXT,
    estado TEXT DEFAULT 'PENDIENTE', prioridad TEXT DEFAULT 'MEDIA', fecha_vencimiento DATE);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_CONTABLE');
INSERT INTO area (nombre_area) VALUES ('ADMINISTRACION'), ('CONTABLE');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) VALUES
 (1, 1, 'Admin Nahan',      'admin@nahan.local',      'hash', 'ACTIVO'),
 (2, 2, 'Responsable Uno',  'responsable@nahan.local','hash', 'ACTIVO'),
 (2, 2, 'Responsable Dos',  'otro@nahan.local',       'hash', 'ACTIVO');

INSERT INTO cliente (razon_social) VALUES ('Cliente de prueba');
INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado) VALUES
 (1, 2, 2, 1, 'Tarea pendiente de Uno',   'PENDIENTE'),
 (1, 2, 2, 1, 'Tarea completada de Uno',  'COMPLETADA'),
 (1, 2, 2, 1, 'Tarea cancelada de Uno',   'CANCELADA'),
 (1, 2, 3, 1, 'Tarea completada de Dos',  'COMPLETADA');
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
    monkeypatch.setattr(tareas_routes, "get_connection", conexion_falsa)

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as cliente_http:
        yield cliente_http


def _login(cliente, email):
    return cliente.post("/api/login", json={"email": email, "password": "x"})


# --------------------------------------------------------------------------

def test_sin_filtro_solo_trae_tareas_no_finalizadas(cliente):
    _login(cliente, "admin@nahan.local")

    tareas = cliente.get("/api/tareas/pendientes").get_json()

    assert {t["titulo"] for t in tareas} == {"Tarea pendiente de Uno"}


def test_filtrar_por_completada_trae_tareas_finalizadas_de_todos(cliente):
    _login(cliente, "admin@nahan.local")

    tareas = cliente.get("/api/tareas/pendientes?estado=COMPLETADA").get_json()

    assert {t["titulo"] for t in tareas} == {
        "Tarea completada de Uno", "Tarea completada de Dos"
    }


def test_el_filtro_se_combina_con_la_restriccion_de_solo_mis_tareas(cliente):
    _login(cliente, "responsable@nahan.local")

    tareas = cliente.get("/api/tareas/pendientes?estado=COMPLETADA").get_json()

    assert {t["titulo"] for t in tareas} == {"Tarea completada de Uno"}


def test_filtrar_por_cancelada(cliente):
    _login(cliente, "admin@nahan.local")

    tareas = cliente.get("/api/tareas/pendientes?estado=CANCELADA").get_json()

    assert {t["titulo"] for t in tareas} == {"Tarea cancelada de Uno"}


def test_un_estado_invalido_responde_400(cliente):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.get("/api/tareas/pendientes?estado=NO_EXISTE")

    assert respuesta.status_code == 400


def test_un_estado_sin_resultados_responde_lista_vacia(cliente):
    _login(cliente, "responsable@nahan.local")

    respuesta = cliente.get("/api/tareas/pendientes?estado=EN_REVISION")

    assert respuesta.status_code == 200
    assert respuesta.get_json() == []
