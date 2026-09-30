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


# --- Estabilización: acceso directo al registro encontrado ---

from pathlib import Path

TOPBAR_JS = Path(__file__).resolve().parents[1] / 'frontend/assets/js/topbar.js'


def test_rf57_cada_resultado_trae_el_tipo_e_id_que_usa_el_enlace(cliente):
    _login(cliente, 'admin@nahan.local')

    resultados = cliente.get('/api/busqueda-global?q=nahan').get_json()['resultados']
    tarea = cliente.get('/api/busqueda-global?q=Tarea propia').get_json()['resultados']['tareas']
    cliente_encontrado = cliente.get('/api/busqueda-global?q=Cliente de').get_json()['resultados']['clientes']

    assert [(u['tipo'], u['id']) for u in resultados['usuarios']] == [('usuario', 1), ('usuario', 2)]
    assert [(t['tipo'], t['id']) for t in tarea] == [('tarea', 20)]
    assert [(c['tipo'], c['id']) for c in cliente_encontrado] == [('cliente', 10)]


def test_rf57_usuario_no_admin_solo_se_encuentra_a_si_mismo(cliente):
    _login(cliente, 'juridica@nahan.local')

    usuarios = cliente.get('/api/busqueda-global?q=nahan').get_json()['resultados']['usuarios']

    assert [u['id'] for u in usuarios] == [2]


def test_rf57_la_respuesta_no_expone_datos_sensibles(cliente):
    _login(cliente, 'admin@nahan.local')

    respuesta = cliente.get('/api/busqueda-global?q=nahan')

    assert 'password' not in respuesta.get_data(as_text=True).lower()
    for usuario in respuesta.get_json()['resultados']['usuarios']:
        assert set(usuario) == {'tipo', 'id', 'nombre', 'detalle'}


def test_rf57_busqueda_global_exige_sesion(cliente):
    assert cliente.get('/api/busqueda-global?q=Tarea').status_code == 401


def test_rf57_el_termino_se_trata_como_dato_y_no_como_sql(cliente, base):
    _login(cliente, 'admin@nahan.local')

    respuesta = cliente.get("/api/busqueda-global", query_string={'q': "x' OR '1'='1"})

    assert respuesta.status_code == 200
    assert respuesta.get_json()['total'] == 0
    assert base.execute('SELECT COUNT(*) FROM tarea').fetchone()[0] == 2


def test_rf57_el_buscador_arma_los_enlaces_con_el_tipo_del_resultado():
    javascript = TOPBAR_JS.read_text(encoding='utf-8')

    # El defecto original: se pasaba el nombre del grupo (plural) a una
    # función que compara contra el tipo en singular, y la URL quedaba en «#».
    assert 'generarUrlResultado({ tipo, id: item.id })' not in javascript
    assert 'tipo: item.tipo || definicion.tipo' in javascript
    for grupo, tipo in (('clientes', 'cliente'), ('tareas', 'tarea'), ('usuarios', 'usuario')):
        assert f'{grupo}: {{ tipo: "{tipo}"' in javascript
    assert 'cliente: "../clientes/ficha_cliente.html"' in javascript
    assert 'tarea: "../tareas/detalle_tarea.html"' in javascript
    assert 'usuario: "../usuarios/modificar_usuario.html"' in javascript


def test_rf57_el_buscador_conserva_minimo_de_caracteres_y_debounce():
    javascript = TOPBAR_JS.read_text(encoding='utf-8')

    assert 'texto.length < 2' in javascript
    assert 'setTimeout(() => ejecutarBusqueda(valor), 250)' in javascript
    assert 'clearTimeout(temporizador)' in javascript
    # La búsqueda la inicia el usuario: debe contar como actividad (RF59).
    inicio = javascript.index('const ejecutarBusqueda')
    assert 'X-Actividad' not in javascript[inicio:javascript.index('busqueda.addEventListener("input"')]
