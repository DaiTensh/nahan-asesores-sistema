# -*- coding: utf-8 -*-
"""RF63 — Visualizando el Detalle Completo de Tarea.

GET /api/tareas/<id> resuelve cliente, responsable, creador y área (no solo
sus id), agrega el historial de auditoria asociado a la tarea y restringe el
acceso a quien no sea ADMINISTRADOR ni el responsable. Corre sobre SQLite en
memoria, igual que test_rf19_redistribucion_tareas.py.
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
    estado TEXT DEFAULT 'PENDIENTE', prioridad TEXT DEFAULT 'MEDIA',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP, fecha_vencimiento DATE,
    fecha_inicio DATETIME, fecha_finalizacion DATETIME, observaciones TEXT);
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tabla_afectada TEXT, accion TEXT, datos_anteriores TEXT, datos_nuevos TEXT,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_CONTABLE');
INSERT INTO area (nombre_area) VALUES ('ADMINISTRACION'), ('CONTABLE');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) VALUES
 (1, 1, 'Admin Nahan',      'admin@nahan.local',      'hash', 'ACTIVO'),
 (2, 2, 'Responsable Uno',  'responsable@nahan.local','hash', 'ACTIVO'),
 (2, 2, 'Otro Usuario',     'otro@nahan.local',       'hash', 'ACTIVO');

INSERT INTO cliente (razon_social) VALUES ('Cliente de prueba');
INSERT INTO tarea (
    id_cliente, id_area, id_responsable, id_creador, titulo, descripcion
) VALUES
 (1, 2, 2, 1, 'Tarea de Responsable Uno', 'Descripción de prueba');

INSERT INTO auditoria (id_usuario, tabla_afectada, accion, datos_anteriores, datos_nuevos) VALUES
 (1, 'tarea', 'REASIGNACION_MASIVA', 'id_tarea=1, id_responsable=3', 'id_tarea=1, id_responsable=2'),
 (1, 'tarea', 'REASIGNACION_MASIVA', 'id_tarea=10, id_responsable=3', 'id_tarea=10, id_responsable=2');
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

def test_el_responsable_ve_el_detalle_con_cliente_area_y_responsable_resueltos(cliente):
    _login(cliente, "responsable@nahan.local")

    respuesta = cliente.get("/api/tareas/1")
    data = respuesta.get_json()

    assert respuesta.status_code == 200
    assert data["cliente"] == "Cliente de prueba"
    assert data["area"] == "CONTABLE"
    assert data["responsable"] == "Responsable Uno"
    assert data["creador"] == "Admin Nahan"


def test_el_administrador_puede_ver_cualquier_tarea(cliente):
    _login(cliente, "admin@nahan.local")

    assert cliente.get("/api/tareas/1").status_code == 200


def test_un_usuario_que_no_es_responsable_ni_administrador_no_puede_ver_la_tarea(cliente):
    _login(cliente, "otro@nahan.local")

    respuesta = cliente.get("/api/tareas/1")

    assert respuesta.status_code == 403


def test_una_tarea_inexistente_responde_404(cliente):
    _login(cliente, "admin@nahan.local")

    assert cliente.get("/api/tareas/999").status_code == 404


def test_el_historial_solo_trae_los_eventos_de_esta_tarea(cliente):
    _login(cliente, "admin@nahan.local")

    data = cliente.get("/api/tareas/1").get_json()

    assert len(data["historial"]) == 1
    assert data["historial"][0]["datos_nuevos"] == "id_tarea=1, id_responsable=2"
