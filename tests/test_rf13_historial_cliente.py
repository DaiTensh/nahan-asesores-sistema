import sqlite3

import pytest

import backend.routes.auth_routes as auth_routes
import backend.utils.auth as auth_utils
from backend.app import app as flask_app
from backend.routes import clientes_routes


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
CREATE TABLE observacion_cliente (
    id_observacion INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cliente INTEGER,
    id_usuario INTEGER,
    texto TEXT,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE documento (
    id_documento INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cliente INTEGER,
    nombre_documento TEXT,
    tipo_documento TEXT,
    url_archivo TEXT,
    descripcion TEXT,
    subido_por INTEGER,
    fecha_subida DATETIME DEFAULT CURRENT_TIMESTAMP,
    estado TEXT DEFAULT 'ACTIVO'
);
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER,
    tabla_afectada TEXT,
    id_registro INTEGER,
    accion TEXT,
    datos_anteriores TEXT,
    datos_nuevos TEXT,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO rol (id_rol, nombre_rol) VALUES (1, 'ADMINISTRADOR'), (2, 'USUARIO_AREA_JURIDICA');
INSERT INTO area (id_area, nombre_area) VALUES (1, 'JURIDICA');
INSERT INTO usuario (id_usuario, id_rol, id_area, nombres, email, password_hash, estado) VALUES
  (1, 1, 1, 'Admin Nahan', 'admin@nahan.local', 'notused', 'ACTIVO'),
  (2, 2, 1, 'Usuario Juridico', 'juridica@nahan.local', 'notused', 'ACTIVO');
INSERT INTO cliente (id_cliente, rut, razon_social, email, telefono, direccion, estado, fecha_creacion) VALUES
  (5, '11.111.111-1', 'Cliente Historial', 'historial@nahan.local', '999', 'Calle 1', 'ACTIVO', '2026-09-10 08:00:00');
INSERT INTO tarea (id_tarea, id_cliente, id_area, id_responsable, titulo, descripcion, estado, fecha_creacion) VALUES
  (7, 5, 1, 2, 'Tarea cliente', 'Revisar documento', 'PENDIENTE', '2026-09-12 09:00:00');
INSERT INTO observacion_cliente (id_observacion, id_cliente, id_usuario, texto, fecha) VALUES
  (11, 5, 2, 'Observación relevante', '2026-09-13 10:00:00');
INSERT INTO documento (id_documento, id_cliente, nombre_documento, tipo_documento, url_archivo, descripcion, subido_por, fecha_subida, estado) VALUES
  (9, 5, 'Contrato', 'Contrato', '/docs/contrato.pdf', 'Documento base', 2, '2026-09-12 18:00:00', 'ACTIVO');
INSERT INTO auditoria (id_usuario, tabla_afectada, id_registro, accion, datos_anteriores, datos_nuevos, fecha) VALUES
  (1, 'cliente', 5, 'CAMBIO_ESTADO', 'estado: ACTIVO', 'estado: INACTIVO', '2026-09-15 18:00:00'),
  (2, 'tarea', 7, 'EDICION', 'id_tarea=7, prioridad=MEDIA', 'id_tarea=7, prioridad=ALTA', '2026-09-14 10:00:00'),
  (2, 'observacion_cliente', 11, 'CREACION', NULL, 'id_observacion=11', '2026-09-13 12:00:00'),
  (2, 'documento', 9, 'REGISTRO', NULL, 'id_documento=9', '2026-09-12 15:00:00');
"""


class _Cursor:
    def __init__(self, conexion, dictionary):
        self._cursor = conexion.cursor()
        self._dictionary = dictionary
        self.lastrowid = None
        self.rowcount = 0

    def execute(self, sql, params=()):
        self._cursor.execute(sql.replace('%s', '?'), tuple(params))
        self.lastrowid = self._cursor.lastrowid
        self.rowcount = self._cursor.rowcount

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
    monkeypatch.setattr(clientes_routes, 'get_connection', conexion_falsa)
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as cliente_http:
        yield cliente_http


def _login(cliente, email):
    respuesta = cliente.post('/api/login', json={'email': email, 'password': 'hash'})
    assert respuesta.status_code == 200


def test_rf13_historial_por_cliente_devuelve_eventos_y_orden_descendente(cliente):
    _login(cliente, 'admin@nahan.local')

    respuesta = cliente.get('/api/clientes/5/historial-completo')
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos['total'] >= 4
    assert [evento['accion'] for evento in datos['historial'][:4]] == ['CAMBIO_ESTADO', 'EDICION', 'CREACION', 'REGISTRO']
    assert datos['historial'][0]['usuario'] == 'Admin Nahan'
    assert 'fecha' in datos['historial'][0] and 'hora' in datos['historial'][0]


def test_rf13_historial_por_cliente_filtra_por_accion_y_fecha(cliente):
    _login(cliente, 'admin@nahan.local')

    respuesta = cliente.get('/api/clientes/5/historial-completo?accion=EDICION&fecha=2026-09-14')
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos['total'] == 1
    assert datos['historial'][0]['accion'] == 'EDICION'


def test_rf13_historial_por_cliente_rechaza_fecha_invalida(cliente):
    _login(cliente, 'admin@nahan.local')

    respuesta = cliente.get('/api/clientes/5/historial-completo?fecha=fecha-mala')

    assert respuesta.status_code == 400


def test_rf13_historial_cliente_inexistente(cliente):
    _login(cliente, 'admin@nahan.local')

    respuesta = cliente.get('/api/clientes/999/historial-completo')

    assert respuesta.status_code == 404
