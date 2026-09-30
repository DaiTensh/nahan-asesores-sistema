# -*- coding: utf-8 -*-
"""RF19 — Reasignando y Redistribuyendo Tareas.

La redistribución masiva reutiliza la misma validación que la reasignación
individual (RF16, _reasignar_tarea en tareas_routes.py) y deja cada
movimiento en auditoria. Corre sobre SQLite en memoria, igual que
test_rf26_restablecimiento.py.
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
    tipo TEXT, importancia TEXT NOT NULL DEFAULT 'NORMAL', mensaje TEXT, url_destino TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
    leida INTEGER DEFAULT 0);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_CONTABLE');
INSERT INTO area (nombre_area) VALUES ('ADMINISTRACION'), ('CONTABLE');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) VALUES
 (1, 1, 'Admin Nahan',    'admin@nahan.local',    'hash', 'ACTIVO'),
 (2, 2, 'Origen Activo',  'origen@nahan.local',   'hash', 'ACTIVO'),
 (2, 2, 'Destino Activo', 'destino@nahan.local',  'hash', 'ACTIVO'),
 (2, 2, 'Cuenta Inactiva','inactivo@nahan.local', 'hash', 'INACTIVO');

INSERT INTO cliente (razon_social) VALUES ('Cliente de prueba');
INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado) VALUES
 (1, 2, 2, 1, 'Tarea 1 de Origen', 'PENDIENTE'),
 (1, 2, 2, 1, 'Tarea 2 de Origen', 'EN_PROCESO'),
 (1, 2, 2, 1, 'Tarea completada de Origen', 'COMPLETADA'),
 (1, 2, 3, 1, 'Tarea de Destino', 'PENDIENTE');
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


def _ids(base, nombres):
    marcadores = ", ".join("?" * len(nombres))
    filas = base.execute(
        f"SELECT id_tarea FROM tarea WHERE titulo IN ({marcadores})", nombres
    ).fetchall()
    return [fila["id_tarea"] for fila in filas]


# --------------------------------------------------------------------------

def test_redistribuye_varias_tareas_en_una_sola_operacion(cliente, base):
    _login(cliente, "admin@nahan.local")
    ids_tarea = _ids(base, ["Tarea 1 de Origen", "Tarea 2 de Origen"])

    respuesta = cliente.put(
        "/api/tareas/reasignar-masivo",
        json={"ids_tarea": ids_tarea, "id_responsable": 3}
    )

    assert respuesta.status_code == 200
    assert respuesta.get_json()["reasignadas"] == 2

    responsables = base.execute(
        f"SELECT id_responsable FROM tarea WHERE id_tarea IN ({', '.join('?' * len(ids_tarea))})",
        ids_tarea
    ).fetchall()
    assert all(fila["id_responsable"] == 3 for fila in responsables)


def test_cada_movimiento_queda_en_auditoria(cliente, base):
    _login(cliente, "admin@nahan.local")
    ids_tarea = _ids(base, ["Tarea 1 de Origen", "Tarea 2 de Origen"])

    cliente.put(
        "/api/tareas/reasignar-masivo",
        json={"ids_tarea": ids_tarea, "id_responsable": 3}
    )

    filas = base.execute(
        "SELECT * FROM auditoria WHERE accion = 'REASIGNACION_MASIVA'"
    ).fetchall()
    assert len(filas) == 2
    assert all(fila["id_usuario"] == 1 for fila in filas)
    assert all("id_responsable=2" in fila["datos_anteriores"] for fila in filas)
    assert all("id_responsable=3" in fila["datos_nuevos"] for fila in filas)


@pytest.mark.parametrize("id_responsable", [4, 999])
def test_un_responsable_invalido_no_deja_reasignaciones_a_medias(cliente, base, id_responsable):
    _login(cliente, "admin@nahan.local")
    ids_tarea = _ids(base, ["Tarea 1 de Origen", "Tarea 2 de Origen"])

    respuesta = cliente.put(
        "/api/tareas/reasignar-masivo",
        json={"ids_tarea": ids_tarea, "id_responsable": id_responsable}
    )

    assert respuesta.status_code == 422
    responsables = base.execute(
        f"SELECT id_responsable FROM tarea WHERE id_tarea IN ({', '.join('?' * len(ids_tarea))})",
        ids_tarea
    ).fetchall()
    assert all(fila["id_responsable"] == 2 for fila in responsables), \
        "ninguna tarea debió moverse: el lote completo se revierte"
    assert base.execute(
        "SELECT COUNT(*) AS n FROM auditoria"
    ).fetchone()["n"] == 0


def test_requiere_al_menos_una_tarea_y_un_responsable(cliente):
    _login(cliente, "admin@nahan.local")

    assert cliente.put(
        "/api/tareas/reasignar-masivo", json={"ids_tarea": [], "id_responsable": 3}
    ).status_code == 400
    assert cliente.put(
        "/api/tareas/reasignar-masivo", json={"ids_tarea": [1], "id_responsable": None}
    ).status_code == 400


def test_muestra_la_carga_de_origen_y_destino_antes_de_confirmar(cliente):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.get("/api/tareas/carga?ids_usuario=2,3")
    carga = respuesta.get_json()

    assert respuesta.status_code == 200
    # El usuario 2 (origen) tiene 2 tareas no finalizadas; la tercera está
    # COMPLETADA y no debe contarse como carga vigente.
    assert carga["2"] == 2
    assert carga["3"] == 1


def test_carga_sin_ids_usuario_responde_400(cliente):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.get("/api/tareas/carga")

    assert respuesta.status_code == 400


@pytest.mark.parametrize("email", ["origen@nahan.local", "destino@nahan.local"])
def test_no_administrador_no_puede_redistribuir(cliente, base, email):
    assert _login(cliente, email).status_code == 200
    anteriores = base.execute("SELECT id_tarea, id_responsable FROM tarea").fetchall()

    respuesta = cliente.put(
        "/api/tareas/reasignar-masivo",
        json={"ids_tarea": [1, 2], "id_responsable": 3}
    )

    assert respuesta.status_code == 403
    assert respuesta.get_json() == {"error": "No tiene permisos para acceder a este recurso"}
    assert base.execute("SELECT id_tarea, id_responsable FROM tarea").fetchall() == anteriores
    assert base.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == 0


def test_no_administrador_no_puede_consultar_carga(cliente):
    assert _login(cliente, "origen@nahan.local").status_code == 200

    respuesta = cliente.get("/api/tareas/carga?ids_usuario=2,3")

    assert respuesta.status_code == 403
    assert respuesta.get_json() == {"error": "No tiene permisos para acceder a este recurso"}


def test_sin_sesion_no_puede_acceder_a_rf19(cliente):
    assert cliente.put(
        "/api/tareas/reasignar-masivo",
        json={"ids_tarea": [1, 2], "id_responsable": 3}
    ).status_code == 401
    assert cliente.get("/api/tareas/carga?ids_usuario=2,3").status_code == 401


def test_tarea_inexistente_revierte_todo_el_lote(cliente, base):
    _login(cliente, "admin@nahan.local")
    anteriores = base.execute("SELECT id_tarea, id_responsable FROM tarea").fetchall()

    respuesta = cliente.put(
        "/api/tareas/reasignar-masivo",
        json={"ids_tarea": [1, 999], "id_responsable": 3}
    )

    assert respuesta.status_code == 404
    assert base.execute("SELECT id_tarea, id_responsable FROM tarea").fetchall() == anteriores
    assert base.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == 0


def test_carga_de_usuario_inexistente_responde_404(cliente):
    _login(cliente, "admin@nahan.local")

    assert cliente.get("/api/tareas/carga?ids_usuario=2,999").status_code == 404


def test_carga_de_usuario_existente_sin_tareas_es_cero(cliente):
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.get("/api/tareas/carga?ids_usuario=1")

    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"1": 0}


@pytest.mark.parametrize('estado', ['COMPLETADA', 'CANCELADA'])
def test_rf19_respeta_bloqueo_final_y_revierte_lote(cliente, base, estado):
    _login(cliente, 'admin@nahan.local')
    base.execute('UPDATE tarea SET estado = ? WHERE id_tarea = 3', (estado,))
    base.commit()
    respuesta = cliente.put('/api/tareas/reasignar-masivo', json={'ids_tarea': [1, 3], 'id_responsable': 3})
    assert respuesta.status_code == 409
    filas = base.execute('SELECT id_responsable FROM tarea WHERE id_tarea IN (1, 3)').fetchall()
    assert all(fila['id_responsable'] == 2 for fila in filas)
    assert base.execute('SELECT COUNT(*) AS n FROM auditoria').fetchone()['n'] == 0
