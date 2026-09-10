# -*- coding: utf-8 -*-
"""RF52 — Notificando Nuevas Asignaciones.

El caso "se notifica al nuevo responsable" ya está cubierto por
test_rf16_reasignacion_individual.py (PUT /api/tareas/<id>/asignar comparte
la misma ruta). Este archivo cubre el criterio de aceptación que falta ahí:
no notificar a quien ejecuta la acción sobre sí mismo.
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
    id_responsable INTEGER, id_creador INTEGER, titulo TEXT, estado TEXT DEFAULT 'PENDIENTE');
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tabla_afectada TEXT, accion TEXT, datos_anteriores TEXT, datos_nuevos TEXT,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE notificacion (
    id_notificacion INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tipo TEXT, mensaje TEXT, url_destino TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
    leida INTEGER DEFAULT 0);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_CONTABLE');
INSERT INTO area (nombre_area) VALUES ('ADMINISTRACION'), ('CONTABLE');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) VALUES
 (1, 1, 'Admin Nahan',   'admin@nahan.local',   'hash', 'ACTIVO'),
 (2, 2, 'Otro Usuario',  'otro@nahan.local',    'hash', 'ACTIVO');

INSERT INTO cliente (razon_social) VALUES ('Cliente de prueba');
INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado) VALUES
 (1, 2, 2, 1, 'Tarea de Otro Usuario', 'PENDIENTE');
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


def _id_tarea(base, titulo):
    return base.execute(
        "SELECT id_tarea FROM tarea WHERE titulo = ?", (titulo,)
    ).fetchone()["id_tarea"]


def test_no_se_notifica_la_autoasignacion(cliente, base):
    _login(cliente, "admin@nahan.local")
    id_tarea = _id_tarea(base, "Tarea de Otro Usuario")

    respuesta = cliente.put(
        f"/api/tareas/{id_tarea}/asignar", json={"id_responsable": 1}
    )

    assert respuesta.status_code == 200
    assert base.execute(
        "SELECT COUNT(*) AS n FROM notificacion"
    ).fetchone()["n"] == 0
