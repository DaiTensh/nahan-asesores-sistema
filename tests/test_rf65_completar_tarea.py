# -*- coding: utf-8 -*-
"""RF65 — Marcando Tarea como Completada.

PUT /api/tareas/<id>/estado con estado=COMPLETADA sigue restringido a
ADMINISTRADOR (igual que hoy con cualquier estado final), pero además
registra fecha_finalizacion y deja en auditoria quién cerró la tarea.
Corre sobre SQLite en memoria, igual que los demás tests de tareas.
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
    id_responsable INTEGER, id_creador INTEGER, titulo TEXT,
    estado TEXT DEFAULT 'PENDIENTE', prioridad TEXT DEFAULT 'MEDIA',
    fecha_finalizacion DATETIME);
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tabla_afectada TEXT, id_registro INTEGER, accion TEXT, datos_anteriores TEXT, datos_nuevos TEXT,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE notificacion (
    id_notificacion INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tipo TEXT, mensaje TEXT, url_destino TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
    leida INTEGER DEFAULT 0);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_CONTABLE');
INSERT INTO area (nombre_area) VALUES ('ADMINISTRACION'), ('CONTABLE');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) VALUES
 (1, 1, 'Admin Nahan',      'admin@nahan.local',      'hash', 'ACTIVO'),
 (2, 2, 'Responsable Uno',  'responsable@nahan.local','hash', 'ACTIVO');

INSERT INTO cliente (razon_social) VALUES ('Cliente de prueba');
INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado) VALUES
 (1, 2, 2, 1, 'Tarea en proceso', 'EN_PROCESO');
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

def test_el_administrador_puede_completar_la_tarea(cliente, base):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.put("/api/tareas/1/estado", json={"estado": "COMPLETADA"})

    assert respuesta.status_code == 200

    fila = base.execute(
        "SELECT estado, fecha_finalizacion FROM tarea WHERE id_tarea = 1"
    ).fetchone()
    assert fila["estado"] == "COMPLETADA"
    assert fila["fecha_finalizacion"] is not None


def test_un_usuario_no_administrador_no_puede_completar_la_tarea(cliente, base):
    _login(cliente, "responsable@nahan.local")

    respuesta = cliente.put("/api/tareas/1/estado", json={"estado": "COMPLETADA"})

    assert respuesta.status_code == 403

    fila = base.execute("SELECT estado FROM tarea WHERE id_tarea = 1").fetchone()
    assert fila["estado"] == "EN_PROCESO"


def test_completar_deja_en_auditoria_quien_cerro_la_tarea(cliente, base):
    _login(cliente, "admin@nahan.local")

    cliente.put("/api/tareas/1/estado", json={"estado": "COMPLETADA"})

    evento = base.execute(
        "SELECT * FROM auditoria WHERE accion = 'COMPLETAR_TAREA'"
    ).fetchone()

    assert evento is not None
    assert evento["id_usuario"] == 1
    assert evento["datos_anteriores"] == "id_tarea=1, estado=EN_PROCESO"
    assert evento["datos_nuevos"] == "id_tarea=1, estado=COMPLETADA"


def test_una_tarea_inexistente_responde_404(cliente):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.put("/api/tareas/999/estado", json={"estado": "COMPLETADA"})

    assert respuesta.status_code == 404


def test_un_estado_operativo_no_registra_fecha_finalizacion_ni_auditoria(cliente, base):
    _login(cliente, "responsable@nahan.local")

    respuesta = cliente.put("/api/tareas/1/estado", json={"estado": "EN_REVISION"})

    assert respuesta.status_code == 200

    fila = base.execute(
        "SELECT estado, fecha_finalizacion FROM tarea WHERE id_tarea = 1"
    ).fetchone()
    assert fila["estado"] == "EN_REVISION"
    assert fila["fecha_finalizacion"] is None
    assert base.execute("SELECT COUNT(*) AS n FROM auditoria").fetchone()["n"] == 2
    assert base.execute("SELECT COUNT(*) AS n FROM auditoria WHERE accion = 'ENVIO_REVISION'").fetchone()["n"] == 2


@pytest.mark.parametrize('estado', ['COMPLETADA', 'CANCELADA'])
def test_no_reabre_ni_edita_prioridad_de_tarea_final(cliente, base, estado):
    _login(cliente, 'admin@nahan.local')
    base.execute('UPDATE tarea SET estado = ? WHERE id_tarea = 1', (estado,))
    base.commit()
    assert cliente.put('/api/tareas/1/estado', json={'estado': 'PENDIENTE'}).status_code == 409
    assert cliente.put('/api/tareas/1/prioridad', json={'prioridad': 'ALTA'}).status_code == 409
    assert base.execute('SELECT estado FROM tarea WHERE id_tarea = 1').fetchone()[0] == estado
    assert base.execute('SELECT COUNT(*) FROM auditoria').fetchone()[0] == 0
