# -*- coding: utf-8 -*-
"""RF54 — Adjuntando Archivos a Tareas.

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
    tabla_afectada TEXT, accion TEXT, datos_anteriores TEXT, datos_nuevos TEXT,
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

@pytest.mark.parametrize("tamano_bytes", [32, 1024 * 1024 - 1, 1024 * 1024])
def test_el_responsable_puede_adjuntar_un_archivo(cliente, base, tmp_path, tamano_bytes):
    _login(cliente, "ivan@nahan.local")

    contenido = b"x" * tamano_bytes
    respuesta = _subir(cliente, 1, "factura.pdf", contenido)

    assert respuesta.status_code == 201
    fila = base.execute("SELECT * FROM documento").fetchone()
    assert fila["nombre_documento"] == "factura.pdf"
    assert fila["subido_por"] == 2
    assert fila["fecha_subida"] is not None

    vinculo = base.execute("SELECT * FROM tarea_documento").fetchone()
    assert vinculo["id_tarea"] == 1
    assert vinculo["id_documento"] == fila["id_documento"]
    assert (tmp_path / fila["url_archivo"]).read_bytes() == contenido
    assert len(list(tmp_path.iterdir())) == 1


def test_un_usuario_ajeno_a_la_tarea_no_puede_adjuntar(cliente):
    _login(cliente, "ajeno@nahan.local")

    respuesta = _subir(cliente, 1, "factura.pdf")

    assert respuesta.status_code == 403


def test_se_rechaza_una_extension_fuera_de_la_lista_blanca(cliente, base, tmp_path):
    _login(cliente, "ivan@nahan.local")

    respuesta = _subir(cliente, 1, "script.exe")

    assert respuesta.status_code == 400
    assert "Tipo de archivo no permitido" in respuesta.get_json()["error"]
    assert base.execute("SELECT COUNT(*) AS n FROM documento").fetchone()["n"] == 0
    assert base.execute("SELECT COUNT(*) AS n FROM tarea_documento").fetchone()["n"] == 0
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("tamano_bytes", [1024 * 1024 + 1, 2 * 1024 * 1024])
def test_se_rechaza_un_archivo_que_supera_el_tamano_configurado(
    cliente, base, tmp_path, tamano_bytes
):
    _login(cliente, "ivan@nahan.local")

    contenido = b"x" * tamano_bytes  # el límite de prueba es 1 MB
    respuesta = _subir(cliente, 1, "grande.pdf", contenido)

    assert respuesta.status_code == 400
    assert respuesta.get_json() == {
        "error": "El archivo supera el tamaño máximo permitido (1 MB)"
    }
    assert base.execute("SELECT COUNT(*) AS n FROM documento").fetchone()["n"] == 0
    assert base.execute("SELECT COUNT(*) AS n FROM tarea_documento").fetchone()["n"] == 0
    assert list(tmp_path.iterdir()) == []


def test_el_limite_se_actualiza_desde_la_base_en_cada_carga(cliente, base, tmp_path):
    _login(cliente, "ivan@nahan.local")
    contenido = b"x" * (1024 * 1024 + 1)

    assert _subir(cliente, 1, "factura.pdf", contenido).status_code == 400
    assert list(tmp_path.iterdir()) == []

    base.execute(
        "UPDATE parametros_sistema SET valor_parametro = ? WHERE nombre_parametro = ?",
        ("2", "ADJUNTOS_TAMANO_MAXIMO_MB")
    )
    base.commit()

    assert _subir(cliente, 1, "factura.pdf", contenido).status_code == 201
    fila = base.execute("SELECT * FROM documento").fetchone()
    assert (tmp_path / fila["url_archivo"]).read_bytes() == contenido

    base.execute(
        "UPDATE parametros_sistema SET valor_parametro = ? WHERE nombre_parametro = ?",
        ("1", "ADJUNTOS_TAMANO_MAXIMO_MB")
    )
    base.commit()

    assert _subir(cliente, 1, "otra.pdf", contenido).status_code == 400
    assert base.execute("SELECT COUNT(*) AS n FROM documento").fetchone()["n"] == 1
    assert base.execute("SELECT COUNT(*) AS n FROM tarea_documento").fetchone()["n"] == 1
    assert list(tmp_path.iterdir()) == [tmp_path / fila["url_archivo"]]
    assert (tmp_path / fila["url_archivo"]).read_bytes() == contenido


def test_el_nombre_en_disco_no_depende_del_nombre_del_cliente(cliente, base, tmp_path):
    _login(cliente, "ivan@nahan.local")

    respuesta = _subir(cliente, 1, "../../etc/passwd.pdf")

    assert respuesta.status_code == 201
    fila = base.execute("SELECT url_archivo FROM documento").fetchone()

    # El nombre guardado nunca es el original: cierra cualquier intento de
    # path traversal desde el nombre que llega del cliente.
    assert fila["url_archivo"] != "../../etc/passwd.pdf"
    assert ".." not in fila["url_archivo"]
    ruta_guardada = tmp_path / fila["url_archivo"]
    assert ruta_guardada.is_file()


def test_una_tarea_inexistente_devuelve_404(cliente):
    _login(cliente, "ivan@nahan.local")

    respuesta = _subir(cliente, 999, "factura.pdf")

    assert respuesta.status_code == 404


def test_archivo_vacio_no_se_persiste(cliente, base, tmp_path):
    _login(cliente, "ivan@nahan.local")
    respuesta = _subir(cliente, 1, 'vacio.pdf', b'')
    assert respuesta.status_code == 400
    assert 'vacío' in respuesta.get_json()['error']
    assert list(tmp_path.iterdir()) == []
    assert base.execute('SELECT COUNT(*) FROM documento').fetchone()[0] == 0
    assert base.execute('SELECT COUNT(*) FROM tarea_documento').fetchone()[0] == 0


@pytest.mark.parametrize('fallo', ['disco', 'asociacion'])
def test_fallo_de_subida_revierte_archivo_y_bd(cliente, base, tmp_path, monkeypatch, fallo):
    from werkzeug.datastructures import FileStorage
    _login(cliente, "ivan@nahan.local")
    if fallo == 'disco':
        def guardar_parcial(self, destino, *args, **kwargs):
            with open(destino, 'wb') as archivo:
                archivo.write(b'parcial')
            raise OSError('Fallo de disco simulado')
        monkeypatch.setattr(FileStorage, 'save', guardar_parcial)
    else:
        original = _Cursor.execute
        def ejecutar(self, sql, params=()):
            if 'INSERT INTO tarea_documento' in sql:
                raise sqlite3.IntegrityError('Fallo de asociación simulado')
            return original(self, sql, params)
        monkeypatch.setattr(_Cursor, 'execute', ejecutar)
    respuesta = _subir(cliente, 1, 'archivo.pdf')
    assert respuesta.status_code == 500
    assert list(tmp_path.iterdir()) == []
    assert base.execute('SELECT COUNT(*) FROM documento').fetchone()[0] == 0
    assert base.execute('SELECT COUNT(*) FROM tarea_documento').fetchone()[0] == 0
