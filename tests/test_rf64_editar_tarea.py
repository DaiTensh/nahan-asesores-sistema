# -*- coding: utf-8 -*-
"""RF64 — Editando Tareas Existentes.

PUT /api/tareas/<id> permite modificar título, descripción, responsable,
prioridad y fecha límite mientras la tarea no esté COMPLETADA ni CANCELADA,
deja cada campo cambiado en auditoria (mismo prefijo "id_tarea=<id>," que lee
RF63) y no permite una fecha de vencimiento anterior a la de creación. Corre
sobre SQLite en memoria, igual que los demás tests de tareas.
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
 (2, 2, 'Responsable Uno',  'responsable@nahan.local','hash', 'ACTIVO'),
 (2, 2, 'Otro Responsable', 'otro@nahan.local',       'hash', 'ACTIVO'),
 (2, 2, 'Cuenta Inactiva',  'inactivo@nahan.local',   'hash', 'INACTIVO'),
 (2, 2, 'Sin Acceso',       'sinacceso@nahan.local',  'hash', 'ACTIVO');

INSERT INTO cliente (razon_social) VALUES ('Cliente de prueba');
INSERT INTO tarea (
    id_cliente, id_area, id_responsable, id_creador, titulo, descripcion,
    estado, prioridad, fecha_creacion, fecha_vencimiento
) VALUES
 (1, 2, 2, 1, 'Tarea editable', 'Descripción original',
  'PENDIENTE', 'MEDIA', '2026-09-01 10:00:00', '2026-09-10'),
 (1, 2, 2, 1, 'Tarea completada', 'Ya cerrada',
  'COMPLETADA', 'MEDIA', '2026-09-01 10:00:00', '2026-09-10');
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


def _payload(**overrides):
    base_payload = {
        "titulo": "Tarea editable (actualizada)",
        "descripcion": "Descripción original",
        "id_responsable": 2,
        "prioridad": "MEDIA",
        "fecha_vencimiento": "2026-09-10"
    }
    base_payload.update(overrides)
    return base_payload


# --------------------------------------------------------------------------

def test_edita_los_campos_y_deja_cada_cambio_en_auditoria(cliente, base):
    _login(cliente, "responsable@nahan.local")

    respuesta = cliente.put(
        "/api/tareas/1",
        json=_payload(titulo="Nuevo título", prioridad="ALTA", id_responsable=3)
    )

    assert respuesta.status_code == 200

    fila = base.execute(
        "SELECT titulo, prioridad, id_responsable FROM tarea WHERE id_tarea = 1"
    ).fetchone()
    assert fila["titulo"] == "Nuevo título"
    assert fila["prioridad"] == "ALTA"
    assert fila["id_responsable"] == 3

    eventos = base.execute(
        "SELECT * FROM auditoria WHERE accion = 'EDICION'"
    ).fetchall()
    campos_auditados = {evento["datos_nuevos"].split(", ")[1].split("=")[0] for evento in eventos}
    assert campos_auditados == {"titulo", "prioridad", "id_responsable"}
    assert all(evento["datos_anteriores"].startswith("id_tarea=1,") for evento in eventos)


def test_no_audita_los_campos_que_no_cambiaron(cliente, base):
    _login(cliente, "responsable@nahan.local")

    cliente.put("/api/tareas/1", json=_payload(titulo="Solo cambia el título"))

    eventos = base.execute(
        "SELECT * FROM auditoria WHERE accion = 'EDICION'"
    ).fetchall()
    assert len(eventos) == 1
    assert "titulo=" in eventos[0]["datos_nuevos"]


def test_una_tarea_completada_no_se_puede_editar(cliente, base):
    _login(cliente, "responsable@nahan.local")

    respuesta = cliente.put("/api/tareas/2", json=_payload())

    assert respuesta.status_code == 409
    assert "COMPLETADA" in respuesta.get_json()["error"] or "CANCELADA" in respuesta.get_json()["error"]

    fila = base.execute("SELECT titulo FROM tarea WHERE id_tarea = 2").fetchone()
    assert fila["titulo"] == "Tarea completada"


def test_la_fecha_de_vencimiento_no_puede_ser_anterior_a_la_fecha_de_creacion(cliente):
    _login(cliente, "responsable@nahan.local")

    respuesta = cliente.put(
        "/api/tareas/1",
        json=_payload(fecha_vencimiento="2026-08-01")
    )

    assert respuesta.status_code == 400


def test_un_responsable_invalido_responde_422(cliente):
    _login(cliente, "responsable@nahan.local")

    assert cliente.put(
        "/api/tareas/1", json=_payload(id_responsable=4)  # cuenta inactiva
    ).status_code == 422


def test_un_usuario_sin_acceso_no_puede_editar_la_tarea(cliente):
    _login(cliente, "sinacceso@nahan.local")

    respuesta = cliente.put("/api/tareas/1", json=_payload())

    assert respuesta.status_code == 403


def test_el_administrador_puede_editar_cualquier_tarea(cliente):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.put("/api/tareas/1", json=_payload(titulo="Editado por admin"))

    assert respuesta.status_code == 200


def test_requiere_titulo_y_responsable(cliente):
    _login(cliente, "responsable@nahan.local")

    assert cliente.put(
        "/api/tareas/1", json=_payload(titulo="")
    ).status_code == 400
    assert cliente.put(
        "/api/tareas/1", json=_payload(id_responsable=None)
    ).status_code == 400
