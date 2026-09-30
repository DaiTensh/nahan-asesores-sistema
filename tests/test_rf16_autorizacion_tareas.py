# -*- coding: utf-8 -*-
"""RF16 / RF52 — Autorización de las operaciones sobre tareas y avisos de
asignación.

Regresión del cierre del Incremento 2:

- PUT /api/tareas/<id>/asignar, /estado y /prioridad solo exigían sesión:
  cualquier usuario podía modificar la tarea de otro cambiando el id en la
  URL. Ahora aplican el mismo acceso que el detalle (RF63) y la edición
  (RF64): ADMINISTRADOR o responsable de la tarea.
- RF52 («al asignar una tarea, avisar al nuevo responsable») solo se cumplía
  en /asignar. Ahora también avisan la creación, la edición que cambia el
  responsable y la redistribución masiva (RF19).

Corre sobre SQLite en memoria, igual que test_rf16_reasignacion_individual.py.
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
    fecha_finalizacion DATETIME);
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tabla_afectada TEXT, id_registro INTEGER, accion TEXT, datos_anteriores TEXT, datos_nuevos TEXT,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE notificacion (
    id_notificacion INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tipo TEXT, importancia TEXT NOT NULL DEFAULT 'NORMAL', mensaje TEXT, url_destino TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
    leida INTEGER DEFAULT 0);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_JURIDICA'), ('USUARIO_AREA_CONTABLE');
INSERT INTO area (nombre_area) VALUES ('JURIDICA'), ('CONTABLE'), ('ADMINISTRACION');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) VALUES
 (1, 3, 'Admin Nahan',       'admin@nahan.local',       'hash', 'ACTIVO'),
 (2, 1, 'Responsable Uno',   'responsable@nahan.local', 'hash', 'ACTIVO'),
 (3, 2, 'Usuario Ajeno',     'ajeno@nahan.local',       'hash', 'ACTIVO'),
 (3, 2, 'Destino Activo',    'destino@nahan.local',     'hash', 'ACTIVO');

INSERT INTO cliente (razon_social) VALUES ('Cliente de prueba');
INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado, prioridad) VALUES
 (1, 1, 2, 1, 'Tarea de Responsable Uno', 'PENDIENTE', 'MEDIA'),
 (1, 1, 2, 1, 'Otra tarea de Responsable Uno', 'EN_PROCESO', 'BAJA');
"""


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
        self._cursor.execute(sql.replace("%s", "?"), tuple(params))
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
    respuesta = cliente.post("/api/login", json={"email": email, "password": "x"})
    assert respuesta.status_code == 200
    return respuesta


def _tarea(base, id_tarea=1):
    return base.execute("SELECT * FROM tarea WHERE id_tarea = ?", (id_tarea,)).fetchone()


def _contar(base, tabla, where="1=1", params=()):
    return base.execute(f"SELECT COUNT(*) AS n FROM {tabla} WHERE {where}", params).fetchone()["n"]


# --- IDOR: un usuario no puede operar sobre la tarea de otro ----------------

def test_usuario_ajeno_no_puede_reasignar_la_tarea_de_otro(cliente, base):
    _login(cliente, "ajeno@nahan.local")

    respuesta = cliente.put("/api/tareas/1/asignar", json={"id_responsable": 3})

    assert respuesta.status_code == 403
    assert _tarea(base)["id_responsable"] == 2
    assert _contar(base, "auditoria", "accion = 'REASIGNACION'") == 0
    assert _contar(base, "notificacion") == 0


def test_usuario_ajeno_no_puede_cambiar_el_estado_de_la_tarea_de_otro(cliente, base):
    _login(cliente, "ajeno@nahan.local")

    respuesta = cliente.put("/api/tareas/1/estado", json={"estado": "EN_PROCESO"})

    assert respuesta.status_code == 403
    assert _tarea(base)["estado"] == "PENDIENTE"
    assert _contar(base, "notificacion") == 0


def test_usuario_ajeno_no_puede_cambiar_la_prioridad_de_la_tarea_de_otro(cliente, base):
    _login(cliente, "ajeno@nahan.local")

    respuesta = cliente.put("/api/tareas/1/prioridad", json={"prioridad": "URGENTE"})

    assert respuesta.status_code == 403
    assert _tarea(base)["prioridad"] == "MEDIA"


@pytest.mark.parametrize("ruta,cuerpo", [
    ("/api/tareas/1/asignar", {"id_responsable": 4}),
    ("/api/tareas/1/estado", {"estado": "EN_REVISION"}),
    ("/api/tareas/1/prioridad", {"prioridad": "ALTA"}),
])
def test_el_responsable_puede_operar_su_propia_tarea(cliente, ruta, cuerpo):
    _login(cliente, "responsable@nahan.local")

    assert cliente.put(ruta, json=cuerpo).status_code == 200


@pytest.mark.parametrize("ruta,cuerpo", [
    ("/api/tareas/1/asignar", {"id_responsable": 4}),
    ("/api/tareas/1/estado", {"estado": "EN_REVISION"}),
    ("/api/tareas/1/prioridad", {"prioridad": "ALTA"}),
])
def test_el_administrador_puede_operar_cualquier_tarea(cliente, ruta, cuerpo):
    _login(cliente, "admin@nahan.local")

    assert cliente.put(ruta, json=cuerpo).status_code == 200


@pytest.mark.parametrize("ruta,cuerpo", [
    ("/api/tareas/999/asignar", {"id_responsable": 4}),
    ("/api/tareas/999/estado", {"estado": "EN_REVISION"}),
    ("/api/tareas/999/prioridad", {"prioridad": "ALTA"}),
])
def test_una_tarea_inexistente_responde_404(cliente, ruta, cuerpo):
    _login(cliente, "ajeno@nahan.local")

    assert cliente.put(ruta, json=cuerpo).status_code == 404


@pytest.mark.parametrize("ruta,cuerpo", [
    ("/api/tareas/1/asignar", {"id_responsable": 4}),
    ("/api/tareas/1/estado", {"estado": "EN_REVISION"}),
    ("/api/tareas/1/prioridad", {"prioridad": "ALTA"}),
])
def test_sin_sesion_responde_401(cliente, ruta, cuerpo):
    assert cliente.put(ruta, json=cuerpo).status_code == 401


def test_un_id_no_numerico_en_la_ruta_no_llega_a_la_tarea(cliente):
    _login(cliente, "ajeno@nahan.local")

    assert cliente.put("/api/tareas/1%20OR%201=1/estado", json={"estado": "EN_PROCESO"}).status_code == 404


# --- RF52: toda nueva asignación avisa al nuevo responsable ------------------

def test_crear_una_tarea_avisa_al_responsable_asignado(cliente, base):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.post("/api/tareas", json={
        "id_cliente": 1, "areas": [1], "id_responsable": 2,
        "titulo": "Tarea nueva asignada", "prioridad": "ALTA",
    })

    assert respuesta.status_code == 201
    aviso = base.execute("SELECT * FROM notificacion WHERE id_usuario = 2").fetchone()
    id_nueva = base.execute("SELECT MAX(id_tarea) AS id FROM tarea").fetchone()["id"]
    assert aviso is not None
    assert aviso["tipo"] == "ASIGNACION_TAREA"
    assert "Tarea nueva asignada" in aviso["mensaje"]
    assert aviso["url_destino"].endswith(f"detalle_tarea.html?id={id_nueva}")


def test_crear_una_tarea_para_uno_mismo_no_genera_aviso(cliente, base):
    _login(cliente, "responsable@nahan.local")

    respuesta = cliente.post("/api/tareas", json={
        "id_cliente": 1, "areas": [1], "id_responsable": 2, "titulo": "Autoasignada",
    })

    assert respuesta.status_code == 201
    assert _contar(base, "notificacion") == 0


def test_editar_el_responsable_avisa_al_nuevo_responsable(cliente, base):
    _login(cliente, "responsable@nahan.local")

    respuesta = cliente.put("/api/tareas/1", json={
        "titulo": "Tarea de Responsable Uno", "descripcion": None,
        "id_responsable": 4, "prioridad": "MEDIA", "fecha_vencimiento": None,
    })

    assert respuesta.status_code == 200
    aviso = base.execute("SELECT * FROM notificacion WHERE id_usuario = 4").fetchone()
    assert aviso is not None
    assert aviso["tipo"] == "REASIGNACION_TAREA"
    assert aviso["url_destino"].endswith("detalle_tarea.html?id=1")


def test_editar_sin_cambiar_responsable_no_genera_aviso(cliente, base):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.put("/api/tareas/1", json={
        "titulo": "Título nuevo", "descripcion": None,
        "id_responsable": 2, "prioridad": "MEDIA", "fecha_vencimiento": None,
    })

    assert respuesta.status_code == 200
    assert _contar(base, "notificacion") == 0


def test_la_redistribucion_masiva_avisa_por_cada_tarea_movida(cliente, base):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.put("/api/tareas/reasignar-masivo", json={
        "ids_tarea": [1, 2], "id_responsable": 4,
    })

    assert respuesta.status_code == 200
    avisos = base.execute(
        "SELECT * FROM notificacion WHERE id_usuario = 4 ORDER BY id_notificacion"
    ).fetchall()
    assert len(avisos) == 2
    assert {a["url_destino"].rsplit("=", 1)[1] for a in avisos} == {"1", "2"}
    assert "Tarea de Responsable Uno" in avisos[0]["mensaje"]


def test_la_redistribucion_al_mismo_responsable_no_genera_aviso(cliente, base):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.put("/api/tareas/reasignar-masivo", json={
        "ids_tarea": [1], "id_responsable": 2,
    })

    assert respuesta.status_code == 200
    assert _contar(base, "notificacion") == 0


# --- Historial (RF63): prioridad rápida y cancelación quedan auditadas -------

def test_cambiar_la_prioridad_queda_en_auditoria(cliente, base):
    _login(cliente, "responsable@nahan.local")

    assert cliente.put("/api/tareas/1/prioridad", json={"prioridad": "URGENTE"}).status_code == 200

    evento = base.execute("SELECT * FROM auditoria WHERE accion = 'EDICION'").fetchone()
    assert evento["id_registro"] == 1
    assert evento["datos_anteriores"] == "id_tarea=1, prioridad=MEDIA"
    assert evento["datos_nuevos"] == "id_tarea=1, prioridad=URGENTE"


def test_repetir_la_misma_prioridad_no_audita(cliente, base):
    _login(cliente, "responsable@nahan.local")

    assert cliente.put("/api/tareas/1/prioridad", json={"prioridad": "MEDIA"}).status_code == 200
    assert _contar(base, "auditoria", "accion = 'EDICION'") == 0


def test_cancelar_una_tarea_deja_quien_la_cancelo(cliente, base):
    _login(cliente, "admin@nahan.local")

    assert cliente.put("/api/tareas/2/estado", json={"estado": "CANCELADA"}).status_code == 200

    evento = base.execute("SELECT * FROM auditoria WHERE accion = 'CANCELAR_TAREA'").fetchone()
    assert evento["id_usuario"] == 1
    assert evento["datos_anteriores"] == "id_tarea=2, estado=EN_PROCESO"
    assert evento["datos_nuevos"] == "id_tarea=2, estado=CANCELADA"


# --- CSRF: un formulario de otro sitio no puede enviar JSON -----------------
# Un <form> de otro origen solo envía text/plain, form-urlencoded o
# multipart sin preflight CORS. Las operaciones de tareas exigen JSON: con
# cualquier otro tipo de cuerpo se rechazan sin modificar nada.

@pytest.mark.parametrize("tipo", ["text/plain", "application/x-www-form-urlencoded"])
@pytest.mark.parametrize("metodo,ruta,cuerpo", [
    ("put", "/api/tareas/1/asignar", '{"id_responsable": 4}'),
    ("put", "/api/tareas/1/estado", '{"estado": "CANCELADA"}'),
    ("put", "/api/tareas/reasignar-masivo", '{"ids_tarea": [1], "id_responsable": 4}'),
    ("post", "/api/tareas", '{"id_cliente": 1, "areas": [1], "id_responsable": 4, "titulo": "x"}'),
])
def test_un_cuerpo_que_no_es_json_se_rechaza(cliente, base, tipo, metodo, ruta, cuerpo):
    _login(cliente, "admin@nahan.local")

    respuesta = getattr(cliente, metodo)(ruta, data=cuerpo, content_type=tipo)

    assert respuesta.status_code in (400, 415)
    assert _tarea(base)["id_responsable"] == 2
    assert _tarea(base)["estado"] == "PENDIENTE"
    assert _contar(base, "tarea") == 2


def test_la_cookie_de_sesion_es_httponly_y_samesite():
    from backend.app import app as flask_app

    assert flask_app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert flask_app.config["SESSION_COOKIE_SAMESITE"] in ("Lax", "Strict")
