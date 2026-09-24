# -*- coding: utf-8 -*-
"""RF55 — Descargando Archivos Asociados a Tareas.

Igual que test_rf26_restablecimiento.py: corre sobre SQLite en memoria para
no depender de un MySQL levantado. Los adjuntos en sí se guardan en un
directorio temporal (tmp_path), nunca dentro del repositorio.
"""
import io
import sqlite3

import pytest

import backend.routes.documentos_routes as documentos_routes
import backend.routes.auth_routes as auth_routes
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
CREATE TABLE documento (
    id_documento INTEGER PRIMARY KEY AUTOINCREMENT, id_cliente INTEGER,
    nombre_documento TEXT, url_archivo TEXT, descripcion TEXT,
    fecha_subida DATETIME DEFAULT CURRENT_TIMESTAMP, subido_por INTEGER,
    estado TEXT DEFAULT 'ACTIVO');
CREATE TABLE tarea_documento (
    id_tarea_documento INTEGER PRIMARY KEY AUTOINCREMENT, id_tarea INTEGER,
    id_documento INTEGER, fecha_asociacion DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tabla_afectada TEXT, id_registro INTEGER, accion TEXT, datos_anteriores TEXT, datos_nuevos TEXT,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE parametros_sistema (
    id_parametro INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_parametro TEXT UNIQUE, valor_parametro TEXT, tipo_dato TEXT, descripcion TEXT);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_CONTABLE');
INSERT INTO area (nombre_area) VALUES ('ADMINISTRACION'), ('CONTABLE');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) VALUES
 (1, 1, 'Admin Nahan',   'admin@nahan.local',   'hash', 'ACTIVO'),
 (2, 2, 'Ivan Gomez',    'ivan@nahan.local',    'hash', 'ACTIVO'),
 (2, 2, 'Ajeno al caso', 'ajeno@nahan.local',   'hash', 'ACTIVO');

INSERT INTO cliente (razon_social) VALUES ('Cliente de prueba');
INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo) VALUES
 (1, 2, 2, 1, 'Tarea de Ivan');

INSERT INTO parametros_sistema (nombre_parametro, valor_parametro, tipo_dato, descripcion) VALUES
 ('ADJUNTOS_TAMANO_MAXIMO_MB', '1', 'INT', 'limite de prueba'),
 ('ADJUNTOS_EXTENSIONES_PERMITIDAS', 'pdf,png', 'VARCHAR', 'extensiones de prueba');
"""


def _traducir(sql):
    return sql.replace("%s", "?")


class _Cursor:
    def __init__(self, conexion):
        self._cursor = conexion.cursor()
        self.lastrowid = None
        self.rowcount = 0

    def execute(self, sql, params=()):
        self._cursor.execute(_traducir(sql), tuple(params))
        self.lastrowid = self._cursor.lastrowid
        self.rowcount = self._cursor.rowcount

    def fetchone(self):
        fila = self._cursor.fetchone()
        return dict(fila) if fila else None

    def fetchall(self):
        return [dict(fila) for fila in self._cursor.fetchall()]

    def close(self):
        pass


class _Conexion:
    def __init__(self, sqlite_conexion):
        self._conexion = sqlite_conexion

    def cursor(self, dictionary=False):
        return _Cursor(self._conexion)

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
def cliente(base, monkeypatch, tmp_path):
    conexion_falsa = lambda: _Conexion(base)

    monkeypatch.setattr(auth_routes, "get_connection", conexion_falsa)
    monkeypatch.setattr(auth_utils, "get_connection", conexion_falsa)
    monkeypatch.setattr(documentos_routes, "get_connection", conexion_falsa)
    monkeypatch.setenv("ADJUNTOS_DIR", str(tmp_path))

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as cliente_http:
        yield cliente_http


def _login(cliente, email):
    return cliente.post("/api/login", json={"email": email, "password": "x"})


def _subir(cliente, id_tarea, nombre, contenido=b"contenido de prueba"):
    return cliente.post(
        f"/api/tareas/{id_tarea}/documentos",
        data={"archivo": (io.BytesIO(contenido), nombre)},
        content_type="multipart/form-data"
    )


# --------------------------------------------------------------------------

def test_listar_documentos_de_una_tarea(cliente):
    _login(cliente, "ivan@nahan.local")
    _subir(cliente, 1, "factura.pdf")

    respuesta = cliente.get("/api/tareas/1/documentos")
    documentos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert len(documentos) == 1
    assert documentos[0]["nombre_documento"] == "factura.pdf"
    assert documentos[0]["subido_por"] == "Ivan Gomez"


def test_un_ajeno_a_la_tarea_no_puede_listar_sus_documentos(cliente):
    _login(cliente, "ivan@nahan.local")
    _subir(cliente, 1, "factura.pdf")

    _login(cliente, "ajeno@nahan.local")
    respuesta = cliente.get("/api/tareas/1/documentos")

    assert respuesta.status_code == 403


def test_el_responsable_puede_descargar_su_adjunto(cliente):
    _login(cliente, "ivan@nahan.local")
    id_documento = _subir(cliente, 1, "factura.pdf", b"contenido real").get_json()["id_documento"]

    respuesta = cliente.get(f"/api/documentos/{id_documento}/descargar")

    assert respuesta.status_code == 200
    assert respuesta.data == b"contenido real"
    assert "factura.pdf" in respuesta.headers["Content-Disposition"]


def test_un_usuario_sin_acceso_a_la_tarea_no_puede_descargar(cliente, base):
    _login(cliente, "ivan@nahan.local")
    id_documento = _subir(cliente, 1, "factura.pdf").get_json()["id_documento"]

    _login(cliente, "ajeno@nahan.local")
    respuesta = cliente.get(f"/api/documentos/{id_documento}/descargar")

    assert respuesta.status_code == 403
    assert base.execute(
        "SELECT COUNT(*) AS n FROM auditoria WHERE accion = 'DESCARGA'"
    ).fetchone()["n"] == 0


def test_un_administrador_puede_descargar_aunque_no_sea_parte_de_la_tarea(cliente):
    _login(cliente, "ivan@nahan.local")
    id_documento = _subir(cliente, 1, "factura.pdf").get_json()["id_documento"]

    _login(cliente, "admin@nahan.local")
    respuesta = cliente.get(f"/api/documentos/{id_documento}/descargar")

    assert respuesta.status_code == 200


def test_la_descarga_exitosa_queda_registrada_en_auditoria(cliente, base):
    _login(cliente, "ivan@nahan.local")
    id_documento = _subir(cliente, 1, "factura.pdf").get_json()["id_documento"]

    cliente.get(f"/api/documentos/{id_documento}/descargar")

    fila = base.execute(
        "SELECT id_usuario, tabla_afectada, accion FROM auditoria WHERE accion = 'DESCARGA'"
    ).fetchone()
    assert fila["id_usuario"] == 2
    assert fila["tabla_afectada"] == "documento"


def test_un_documento_inexistente_devuelve_404(cliente):
    _login(cliente, "ivan@nahan.local")

    respuesta = cliente.get("/api/documentos/999/descargar")

    assert respuesta.status_code == 404


def test_creador_sin_responsabilidad_no_tiene_acceso_a_adjuntos(cliente, base):
    _login(cliente, 'ivan@nahan.local')
    id_documento = _subir(cliente, 1, 'factura.pdf').get_json()['id_documento']
    base.execute('UPDATE tarea SET id_creador = 3 WHERE id_tarea = 1')
    base.commit()
    _login(cliente, 'ajeno@nahan.local')
    assert cliente.get('/api/tareas/1/documentos').status_code == 403
    assert cliente.get(f'/api/documentos/{id_documento}/descargar').status_code == 403
    assert _subir(cliente, 1, 'rechazado.pdf').status_code == 403
    assert base.execute('SELECT COUNT(*) AS n FROM documento').fetchone()['n'] == 1
    assert base.execute('SELECT COUNT(*) AS n FROM tarea_documento').fetchone()['n'] == 1
    assert base.execute("SELECT COUNT(*) AS n FROM auditoria WHERE accion = 'DESCARGA'").fetchone()['n'] == 0
