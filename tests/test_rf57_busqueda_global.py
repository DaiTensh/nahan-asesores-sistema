import sqlite3

import pytest

import backend.routes.auth_routes as auth_routes
import backend.utils.auth as auth_utils
from backend.app import app as flask_app
from backend.routes import busqueda_routes


ESQUEMA = """
CREATE TABLE rol (id_rol INTEGER PRIMARY KEY AUTOINCREMENT, nombre_rol TEXT);
CREATE TABLE area (id_area INTEGER PRIMARY KEY AUTOINCREMENT, nombre_area TEXT);
CREATE TABLE usuario (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    id_rol INTEGER,
    id_area INTEGER,
    nombres TEXT,
    email TEXT,
    password_hash TEXT,
    estado TEXT DEFAULT 'ACTIVO'
);
CREATE TABLE cliente (
    id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
    rut TEXT,
    razon_social TEXT,
    email TEXT,
    telefono TEXT,
    direccion TEXT,
    estado TEXT DEFAULT 'ACTIVO',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE tarea (
    id_tarea INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cliente INTEGER,
    id_area INTEGER,
    id_responsable INTEGER,
    titulo TEXT,
    descripcion TEXT,
    estado TEXT,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO rol (id_rol, nombre_rol) VALUES (1, 'ADMINISTRADOR'), (2, 'USUARIO_AREA_JURIDICA');
INSERT INTO area (id_area, nombre_area) VALUES (1, 'JURIDICA');
INSERT INTO usuario (id_usuario, id_rol, id_area, nombres, email, password_hash, estado) VALUES
  (1, 1, 1, 'Admin Nahan', 'admin@nahan.local', 'notused', 'ACTIVO'),
  (2, 2, 1, 'Usuario Juridico', 'juridica@nahan.local', 'notused', 'ACTIVO');
INSERT INTO cliente (id_cliente, rut, razon_social, email, telefono, direccion, estado) VALUES
  (10, '22.222.222-2', 'Cliente de prueba', 'cliente@nahan.local', '777', 'Calle Norte', 'ACTIVO');
INSERT INTO tarea (id_tarea, id_cliente, id_area, id_responsable, titulo, descripcion, estado) VALUES
  (20, 10, 1, 2, 'Tarea propia', 'Revisión de contrato', 'PENDIENTE'),
  (21, 10, 1, 1, 'Tarea ajena', 'Datos sensibles del cliente', 'PENDIENTE');
"""


class _Cursor:
    def __init__(self, conexion, dictionary=False):
        self._cursor = conexion.cursor()
        self._dictionary = dictionary

    def execute(self, sql, params=()):
        self._cursor.execute(sql.replace('%s', '?'), tuple(params))

    def fetchone(self):
        fila = self._cursor.fetchone()
        if fila is None:
            return None
        return dict(fila) if self._dictionary else tuple(fila)

    def fetchall(self):
        return [dict(fila) for fila in self._cursor.fetchall()] if self._dictionary else self._cursor.fetchall()

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

    conexion = sqlite3.connect(':memory:')
    conexion.row_factory = sqlite3.Row
    conexion.executescript(ESQUEMA)
    conexion.execute("UPDATE usuario SET password_hash = ? WHERE id_usuario = 1", (hash_password('hash'),))
    conexion.execute("UPDATE usuario SET password_hash = ? WHERE id_usuario = 2", (hash_password('hash'),))
    conexion.commit()
    yield conexion
    conexion.close()


@pytest.fixture
def cliente(base, monkeypatch):
    conexion_falsa = lambda: _Conexion(base)
    monkeypatch.setattr(auth_routes, 'get_connection', conexion_falsa)
    monkeypatch.setattr(auth_utils, 'get_connection', conexion_falsa)
    monkeypatch.setattr(busqueda_routes, 'get_connection', conexion_falsa)
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as cliente_http:
        yield cliente_http


def _login(cliente, email):
    respuesta = cliente.post('/api/login', json={'email': email, 'password': 'hash'})
    assert respuesta.status_code == 200


def test_rf57_busqueda_global_admin_agrupa_resultados(cliente):
    _login(cliente, 'admin@nahan.local')

    respuesta = cliente.get('/api/busqueda-global?q=Tarea')
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert set(datos['resultados']) == {'clientes', 'tareas', 'usuarios'}
    assert any(item['nombre'] == 'Tarea ajena' for item in datos['resultados']['tareas'])


def test_rf57_busqueda_global_usuario_no_admin_no_ve_tareas_ajenas(cliente):
    _login(cliente, 'juridica@nahan.local')

    respuesta = cliente.get('/api/busqueda-global?q=Tarea')
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert [item['nombre'] for item in datos['resultados']['tareas']] == ['Tarea propia']
    assert all('Datos sensibles' not in (item.get('detalle') or '') for item in datos['resultados']['tareas'])


def test_rf57_busqueda_global_rechaza_consulta_corta(cliente):
    _login(cliente, 'admin@nahan.local')

    respuesta = cliente.get('/api/busqueda-global?q=T')

    assert respuesta.status_code == 400
