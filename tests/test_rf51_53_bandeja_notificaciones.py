# -*- coding: utf-8 -*-
"""RF51 / RF52 / RF53 — Consulta de las notificaciones internas.

Los avisos se generaban (cambio de estado, asignación, vencimiento) pero no
existía forma de verlos. Este archivo cubre la bandeja mínima que cierra esos
RF en el Incremento 2:

- GET /api/notificaciones: solo las del usuario en sesión, más recientes
  primero, con el total de no leídas.
- GET /api/notificaciones/contador: no leídas del usuario en sesión.
- PUT /api/notificaciones/<id>/leida: marca una propia; una ajena o
  inexistente responde 404 (no revela que existe).
- PUT /api/notificaciones/leer-todas: solo afecta a las propias.

Además recorre el flujo completo evento -> notificación -> consulta ->
marcar como leída para RF51.

Corre sobre SQLite en memoria, como el resto de las pruebas de tareas.
"""
import sqlite3

import pytest

import backend.routes.auth_routes as auth_routes
import backend.routes.notificaciones_routes as notificaciones_routes
import backend.routes.tareas_routes as tareas_routes
import backend.utils.auth as auth_utils
from backend.app import app as flask_app

ESQUEMA = """
CREATE TABLE rol (id_rol INTEGER PRIMARY KEY AUTOINCREMENT, nombre_rol TEXT);
CREATE TABLE area (id_area INTEGER PRIMARY KEY AUTOINCREMENT, nombre_area TEXT);
CREATE TABLE usuario (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT, id_rol INTEGER, id_area INTEGER,
    nombres TEXT, email TEXT UNIQUE, password_hash TEXT, estado TEXT DEFAULT 'ACTIVO');
CREATE TABLE tarea (
    id_tarea INTEGER PRIMARY KEY AUTOINCREMENT, id_cliente INTEGER, id_area INTEGER,
    id_responsable INTEGER, id_creador INTEGER, titulo TEXT, estado TEXT DEFAULT 'PENDIENTE',
    fecha_finalizacion DATETIME);
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tabla_afectada TEXT, id_registro INTEGER, accion TEXT, datos_anteriores TEXT, datos_nuevos TEXT,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE notificacion (
    id_notificacion INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tipo TEXT, mensaje TEXT, url_destino TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
    leida INTEGER DEFAULT 0);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_JURIDICA');
INSERT INTO area (nombre_area) VALUES ('JURIDICA'), ('ADMINISTRACION');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) VALUES
 (1, 2, 'Admin Nahan', 'admin@nahan.local', 'hash', 'ACTIVO'),
 (2, 1, 'Usuario Uno', 'uno@nahan.local',   'hash', 'ACTIVO'),
 (2, 1, 'Usuario Dos', 'dos@nahan.local',   'hash', 'ACTIVO');

INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado) VALUES
 (1, 1, 2, 1, 'Tarea de Usuario Uno', 'PENDIENTE');

INSERT INTO notificacion (id_usuario, tipo, mensaje, url_destino, fecha, leida) VALUES
 (2, 'ASIGNACION_TAREA',   'Aviso antiguo de Uno',  '/frontend/tareas/detalle_tarea.html?id=1', '2026-09-01 10:00:00', 1),
 (2, 'VENCIMIENTO_PROXIMO', 'Aviso reciente de Uno', '/frontend/tareas/detalle_tarea.html?id=1', '2026-09-10 10:00:00', 0),
 (3, 'ASIGNACION_TAREA',   'Aviso privado de Dos',  '/frontend/tareas/detalle_tarea.html?id=9', '2026-09-05 10:00:00', 0);
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
    monkeypatch.setattr(notificaciones_routes, "get_connection", conexion_falsa)

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as cliente_http:
        yield cliente_http


def _login(cliente, email):
    assert cliente.post("/api/login", json={"email": email, "password": "x"}).status_code == 200


def _leida(base, id_notificacion):
    return base.execute(
        "SELECT leida FROM notificacion WHERE id_notificacion = ?", (id_notificacion,)
    ).fetchone()["leida"]


def test_sin_sesion_no_se_puede_consultar(cliente):
    assert cliente.get("/api/notificaciones").status_code == 401
    assert cliente.get("/api/notificaciones/contador").status_code == 401
    assert cliente.put("/api/notificaciones/1/leida").status_code == 401
    assert cliente.put("/api/notificaciones/leer-todas").status_code == 401


def test_lista_solo_las_propias_mas_recientes_primero(cliente):
    _login(cliente, "uno@nahan.local")

    respuesta = cliente.get("/api/notificaciones")
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert [n["mensaje"] for n in datos["notificaciones"]] == [
        "Aviso reciente de Uno", "Aviso antiguo de Uno",
    ]
    assert datos["no_leidas"] == 1
    assert datos["notificaciones"][0]["leida"] is False
    assert datos["notificaciones"][1]["leida"] is True
    assert all("privado" not in n["mensaje"] for n in datos["notificaciones"])


def test_filtra_solo_no_leidas_y_respeta_el_limite(cliente):
    _login(cliente, "uno@nahan.local")

    solo_no_leidas = cliente.get("/api/notificaciones?solo_no_leidas=1").get_json()
    limitadas = cliente.get("/api/notificaciones?limite=1").get_json()

    assert [n["mensaje"] for n in solo_no_leidas["notificaciones"]] == ["Aviso reciente de Uno"]
    assert len(limitadas["notificaciones"]) == 1


@pytest.mark.parametrize("limite", ["0", "-1", "abc", "1;DROP"])
def test_un_limite_invalido_responde_400(cliente, limite):
    _login(cliente, "uno@nahan.local")

    assert cliente.get(f"/api/notificaciones?limite={limite}").status_code == 400


def test_el_contador_solo_cuenta_las_no_leidas_propias(cliente):
    _login(cliente, "uno@nahan.local")

    assert cliente.get("/api/notificaciones/contador").get_json() == {"no_leidas": 1}


def test_marcar_una_propia_como_leida(cliente, base):
    _login(cliente, "uno@nahan.local")

    respuesta = cliente.put("/api/notificaciones/2/leida")

    assert respuesta.status_code == 200
    assert respuesta.get_json()["no_leidas"] == 0
    assert _leida(base, 2) == 1


def test_no_se_puede_marcar_la_notificacion_de_otro_usuario(cliente, base):
    _login(cliente, "uno@nahan.local")

    respuesta = cliente.put("/api/notificaciones/3/leida")

    assert respuesta.status_code == 404
    assert _leida(base, 3) == 0


def test_una_notificacion_inexistente_responde_404(cliente):
    _login(cliente, "uno@nahan.local")

    assert cliente.put("/api/notificaciones/999/leida").status_code == 404


def test_marcar_todas_solo_afecta_a_las_propias(cliente, base):
    _login(cliente, "uno@nahan.local")

    respuesta = cliente.put("/api/notificaciones/leer-todas")

    assert respuesta.status_code == 200
    assert respuesta.get_json()["marcadas"] == 1
    assert _leida(base, 2) == 1
    assert _leida(base, 3) == 0


def test_el_administrador_tampoco_ve_las_de_otros(cliente):
    _login(cliente, "admin@nahan.local")

    datos = cliente.get("/api/notificaciones").get_json()

    assert datos == {"notificaciones": [], "no_leidas": 0}


def test_flujo_completo_cambio_de_estado_consulta_y_lectura(cliente, base):
    """RF51 de punta a punta: el administrador cambia el estado, el
    responsable ve el aviso en su bandeja con el enlace a la tarea y lo marca
    como leído."""
    _login(cliente, "admin@nahan.local")
    assert cliente.put("/api/tareas/1/estado", json={"estado": "EN_PROCESO"}).status_code == 200
    cliente.post("/api/logout")

    _login(cliente, "uno@nahan.local")
    datos = cliente.get("/api/notificaciones?solo_no_leidas=1").get_json()
    aviso = datos["notificaciones"][0]

    assert aviso["tipo"] == "CAMBIO_ESTADO_TAREA"
    assert "PENDIENTE" in aviso["mensaje"] and "EN_PROCESO" in aviso["mensaje"]
    assert aviso["url_destino"] == "/frontend/tareas/detalle_tarea.html?id=1"
    assert datos["no_leidas"] == 2

    assert cliente.put(f"/api/notificaciones/{aviso['id_notificacion']}/leida").status_code == 200
    assert cliente.get("/api/notificaciones/contador").get_json() == {"no_leidas": 1}
