# -*- coding: utf-8 -*-
"""RF16 — Modificando la Asignación de Tareas.

PUT /api/tareas/<id>/asignar deja el cambio en auditoria con responsable
anterior y nuevo, notifica al nuevo responsable (tabla notificacion, a falta
de la función de notificación de Vicente) y no permite reasignar una tarea
COMPLETADA o CANCELADA. Corre sobre SQLite en memoria, igual que
test_rf19_redistribucion_tareas.py (comparte _reasignar_tarea con esa ruta).
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
 (2, 2, 'Origen Activo',    'origen@nahan.local',     'hash', 'ACTIVO'),
 (2, 2, 'Destino Activo',   'destino@nahan.local',    'hash', 'ACTIVO'),
 (2, 2, 'Cuenta Inactiva',  'inactivo@nahan.local',   'hash', 'INACTIVO');

INSERT INTO cliente (razon_social) VALUES ('Cliente de prueba');
INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado) VALUES
 (1, 2, 2, 1, 'Tarea pendiente de Origen', 'PENDIENTE'),
 (1, 2, 2, 1, 'Tarea completada de Origen', 'COMPLETADA');
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
    # RF30 audita el inicio de sesión. Esta prueba no trata de sesiones y cuenta
    # sus propios eventos, así que el login que usa como preparación no debe
    # sumar uno; el LOGIN real se comprueba en test_rf30_historial_accesos.py.
    monkeypatch.setattr(auth_routes, "registrar_auditoria", lambda *args, **kwargs: None)
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


# --------------------------------------------------------------------------

def test_reasigna_la_tarea(cliente, base):
    _login(cliente, "admin@nahan.local")
    id_tarea = _id_tarea(base, "Tarea pendiente de Origen")

    respuesta = cliente.put(
        f"/api/tareas/{id_tarea}/asignar", json={"id_responsable": 3}
    )

    assert respuesta.status_code == 200
    fila = base.execute(
        "SELECT id_responsable FROM tarea WHERE id_tarea = ?", (id_tarea,)
    ).fetchone()
    assert fila["id_responsable"] == 3


def test_deja_en_auditoria_el_responsable_anterior_y_el_nuevo(cliente, base):
    _login(cliente, "admin@nahan.local")
    id_tarea = _id_tarea(base, "Tarea pendiente de Origen")

    cliente.put(f"/api/tareas/{id_tarea}/asignar", json={"id_responsable": 3})

    evento = base.execute(
        "SELECT * FROM auditoria WHERE accion = 'REASIGNACION'"
    ).fetchone()

    assert evento is not None
    assert evento["datos_anteriores"] == f"id_tarea={id_tarea}, id_responsable=2"
    assert evento["datos_nuevos"] == f"id_tarea={id_tarea}, id_responsable=3"


def test_el_nuevo_responsable_recibe_una_notificacion(cliente, base):
    _login(cliente, "admin@nahan.local")
    id_tarea = _id_tarea(base, "Tarea pendiente de Origen")

    cliente.put(f"/api/tareas/{id_tarea}/asignar", json={"id_responsable": 3})

    notificacion = base.execute(
        "SELECT * FROM notificacion WHERE id_usuario = 3"
    ).fetchone()

    assert notificacion is not None
    assert "Tarea pendiente de Origen" in notificacion["mensaje"]
    assert str(id_tarea) in notificacion["url_destino"]


def test_no_se_puede_reasignar_una_tarea_completada_o_cancelada(cliente, base):
    _login(cliente, "admin@nahan.local")
    id_tarea = _id_tarea(base, "Tarea completada de Origen")

    respuesta = cliente.put(
        f"/api/tareas/{id_tarea}/asignar", json={"id_responsable": 3}
    )

    assert respuesta.status_code == 409
    fila = base.execute(
        "SELECT id_responsable FROM tarea WHERE id_tarea = ?", (id_tarea,)
    ).fetchone()
    assert fila["id_responsable"] == 2
    assert base.execute("SELECT COUNT(*) AS n FROM auditoria").fetchone()["n"] == 0
    assert base.execute("SELECT COUNT(*) AS n FROM notificacion").fetchone()["n"] == 0


def test_un_responsable_invalido_responde_422(cliente, base):
    _login(cliente, "admin@nahan.local")
    id_tarea = _id_tarea(base, "Tarea pendiente de Origen")

    respuesta = cliente.put(
        f"/api/tareas/{id_tarea}/asignar", json={"id_responsable": 4}  # inactiva
    )

    assert respuesta.status_code == 422


def test_una_tarea_inexistente_responde_404(cliente):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.put("/api/tareas/999/asignar", json={"id_responsable": 3})

    assert respuesta.status_code == 404


def test_requiere_un_responsable(cliente):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.put("/api/tareas/1/asignar", json={})

    assert respuesta.status_code == 400
