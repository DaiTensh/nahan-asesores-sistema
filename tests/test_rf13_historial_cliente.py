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
    # RF30 audita el inicio de sesión. Esta prueba no trata de sesiones y cuenta
    # sus propios eventos, así que el login que usa como preparación no debe
    # sumar uno; el LOGIN real se comprueba en test_rf30_historial_accesos.py.
    monkeypatch.setattr(auth_routes, "registrar_auditoria", lambda *args, **kwargs: None)
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


# --- Estabilización: validación del rango de fechas e interfaz en la ficha ---

from pathlib import Path

FRONTEND_CLIENTES = Path(__file__).resolve().parents[1] / 'frontend/clientes'
URL_HISTORIAL = '/api/clientes/5/historial-completo'


@pytest.mark.parametrize('valor', ['xx', '2026-13-01', '2026-02-30', '14-09-2026', '2026/09/14'])
def test_rf13_fecha_inicio_invalida_responde_400(cliente, valor):
    _login(cliente, 'admin@nahan.local')

    respuesta = cliente.get(URL_HISTORIAL, query_string={'fecha_inicio': valor})

    assert respuesta.status_code == 400
    assert 'AAAA-MM-DD' in respuesta.get_json()['error']


@pytest.mark.parametrize('valor', ['xx', '2026-13-01', '2026-02-30', '14-09-2026', '2026/09/14'])
def test_rf13_fecha_fin_invalida_responde_400(cliente, valor):
    _login(cliente, 'admin@nahan.local')

    respuesta = cliente.get(URL_HISTORIAL, query_string={'fecha_fin': valor})

    assert respuesta.status_code == 400
    assert 'AAAA-MM-DD' in respuesta.get_json()['error']


def test_rf13_rango_invertido_responde_400(cliente):
    _login(cliente, 'admin@nahan.local')

    respuesta = cliente.get(URL_HISTORIAL + '?fecha_inicio=2026-09-15&fecha_fin=2026-09-12')

    assert respuesta.status_code == 400
    assert 'posterior' in respuesta.get_json()['error']


def test_rf13_la_validacion_de_fechas_precede_a_la_busqueda_del_cliente(cliente):
    _login(cliente, 'admin@nahan.local')

    assert cliente.get('/api/clientes/999/historial-completo?fecha_fin=xx').status_code == 400
    assert cliente.get('/api/clientes/999/historial-completo?fecha_fin=2026-09-15').status_code == 404


def test_rf13_rango_de_fechas_incluye_ambos_extremos(cliente):
    _login(cliente, 'admin@nahan.local')

    datos = cliente.get(URL_HISTORIAL + '?fecha_inicio=2026-09-13&fecha_fin=2026-09-14').get_json()

    assert [evento['accion'] for evento in datos['historial']] == ['EDICION', 'CREACION']
    assert datos['total'] == 2


def test_rf13_se_puede_filtrar_solo_desde_o_solo_hasta(cliente):
    _login(cliente, 'admin@nahan.local')

    desde = cliente.get(URL_HISTORIAL + '?fecha_inicio=2026-09-14').get_json()
    hasta = cliente.get(URL_HISTORIAL + '?fecha_fin=2026-09-12').get_json()

    assert [evento['accion'] for evento in desde['historial']] == ['CAMBIO_ESTADO', 'EDICION']
    assert [evento['accion'] for evento in hasta['historial']] == ['REGISTRO']


def test_rf13_orden_cronologico_descendente_con_fecha_hora_y_usuario(cliente):
    _login(cliente, 'admin@nahan.local')

    historial = cliente.get(URL_HISTORIAL).get_json()['historial']

    momentos = [f"{evento['fecha']} {evento['hora']}" for evento in historial]
    assert momentos == sorted(momentos, reverse=True)
    assert momentos[0] == '2026-09-15 18:00:00'
    assert all(evento['usuario'] and evento['accion'] for evento in historial)


def test_rf13_filtro_por_accion_y_acciones_disponibles(cliente):
    _login(cliente, 'admin@nahan.local')

    datos = cliente.get(URL_HISTORIAL + '?accion=REGISTRO').get_json()

    assert [evento['accion'] for evento in datos['historial']] == ['REGISTRO']
    # El selector ofrece todas las acciones del cliente, no solo la filtrada.
    assert datos['acciones_disponibles'] == ['CAMBIO_ESTADO', 'CREACION', 'EDICION', 'REGISTRO']


def test_rf13_accion_inexistente_devuelve_lista_vacia_sin_error(cliente):
    _login(cliente, 'admin@nahan.local')

    respuesta = cliente.get(URL_HISTORIAL, query_string={'accion': "X' OR '1'='1"})

    assert respuesta.status_code == 200
    assert respuesta.get_json()['historial'] == []


def test_rf13_paginacion_con_limite_y_offset(cliente):
    _login(cliente, 'admin@nahan.local')

    pagina = cliente.get(URL_HISTORIAL + '?limite=2&offset=2').get_json()

    assert pagina['total'] == 4
    assert [evento['accion'] for evento in pagina['historial']] == ['CREACION', 'REGISTRO']


def test_rf13_usuario_de_area_puede_consultar_y_sin_sesion_no(cliente):
    assert cliente.get(URL_HISTORIAL).status_code == 401

    _login(cliente, 'juridica@nahan.local')
    assert cliente.get(URL_HISTORIAL).status_code == 200


def test_rf13_el_historial_es_de_solo_lectura(cliente, base):
    _login(cliente, 'admin@nahan.local')

    for metodo in (cliente.post, cliente.put, cliente.patch, cliente.delete):
        assert metodo(URL_HISTORIAL).status_code == 405
    cliente.get(URL_HISTORIAL)
    assert base.execute('SELECT COUNT(*) FROM auditoria').fetchone()[0] == 4


def test_rf13_la_ficha_del_cliente_tiene_la_seccion_historial():
    html = (FRONTEND_CLIENTES / 'ficha_cliente.html').read_text(encoding='utf-8')
    javascript = (FRONTEND_CLIENTES / 'ficha_cliente.js').read_text(encoding='utf-8')

    for identificador in ('seccionHistorial', 'formHistorialCliente', 'historialAccion',
                          'historialFechaInicio', 'historialFechaFin', 'tablaHistorialCuerpo',
                          'btnHistorialAnterior', 'btnHistorialSiguiente'):
        assert f'id="{identificador}"' in html
        assert f'"{identificador}"' in javascript
    assert '/historial-completo?' in javascript
    assert 'cargarHistorial();' in javascript
    # Solo lectura: la sección consulta, no envía cambios.
    seccion = javascript[javascript.index('// RF13'):]
    assert 'method:' not in seccion
    assert 'innerHTML' not in seccion


def test_rf13_el_limite_por_pagina_tiene_un_maximo(cliente, base):
    _login(cliente, 'admin@nahan.local')
    base.executemany(
        "INSERT INTO auditoria (id_usuario, tabla_afectada, id_registro, accion) VALUES (1, 'cliente', 5, 'CAMBIO_ESTADO')",
        [()] * 250,
    )
    base.commit()

    datos = cliente.get(URL_HISTORIAL + '?limite=100000').get_json()

    assert datos['total'] == 254
    assert len(datos['historial']) == clientes_routes.HISTORIAL_LIMITE_MAXIMO == 200
