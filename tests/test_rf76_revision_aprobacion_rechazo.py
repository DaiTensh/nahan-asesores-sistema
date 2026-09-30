# -*- coding: utf-8 -*-
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
    nombres TEXT, email TEXT UNIQUE, password_hash TEXT, estado TEXT DEFAULT 'ACTIVO'
);
CREATE TABLE cliente (
    id_cliente INTEGER PRIMARY KEY AUTOINCREMENT, razon_social TEXT
);
CREATE TABLE tarea (
    id_tarea INTEGER PRIMARY KEY AUTOINCREMENT, id_cliente INTEGER, id_area INTEGER,
    id_responsable INTEGER, id_creador INTEGER, titulo TEXT, descripcion TEXT,
    estado TEXT DEFAULT 'PENDIENTE', prioridad TEXT DEFAULT 'MEDIA',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP, fecha_vencimiento DATE,
    fecha_inicio DATETIME, fecha_finalizacion DATETIME, observaciones TEXT
);
CREATE TABLE revision_tarea (
    id_revision INTEGER PRIMARY KEY AUTOINCREMENT,
    id_tarea INTEGER,
    id_revisor INTEGER,
    accion TEXT,
    observaciones TEXT,
    fecha_revision DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tabla_afectada TEXT, id_registro INTEGER, accion TEXT, datos_anteriores TEXT, datos_nuevos TEXT,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE notificacion (
    id_notificacion INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tipo TEXT, importancia TEXT NOT NULL DEFAULT 'NORMAL', mensaje TEXT, url_destino TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
    leida INTEGER DEFAULT 0
);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_JURIDICA'), ('USUARIO_AREA_CONTABLE');
INSERT INTO area (nombre_area) VALUES ('JURIDICA'), ('CONTABLE');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) VALUES
  (1, 1, 'Admin Nahan', 'admin@nahan.local', 'hash', 'ACTIVO'),
  (2, 1, 'Responsable Uno', 'responsable@nahan.local', 'hash', 'ACTIVO'),
  (3, 2, 'Usuario Ajeno', 'ajeno@nahan.local', 'hash', 'ACTIVO');
INSERT INTO cliente (razon_social) VALUES ('Cliente de prueba');
INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado, prioridad) VALUES
  (1, 1, 2, 1, 'Tarea en revisión', 'EN_PROCESO', 'MEDIA'),
  (1, 1, 2, 1, 'Tarea completada', 'COMPLETADA', 'MEDIA');
"""


class _Cursor:
    """Cursor SQLite que imita al cursor sin buffer de mysql-connector.

    Con el conector real, ejecutar una sentencia mientras la anterior todavía
    tiene filas sin leer lanza «Unread result found». SQLite lo tolera, y por
    eso las pruebas originales no detectaron el defecto de RF76. Aquí se
    reproduce la regla: el resultado de un SELECT queda pendiente hasta que
    una lectura llega al final de las filas.
    """

    def __init__(self, conexion, dictionary):
        self._cursor = conexion.cursor()
        self._dictionary = dictionary
        self._filas = []
        self._sin_leer = False
        self.lastrowid = None
        self.rowcount = 0

    def _empaquetar(self, fila):
        if fila is None:
            return None
        return dict(fila) if self._dictionary else tuple(fila)

    def execute(self, sql, params=()):
        if self._sin_leer:
            raise RuntimeError("Unread result found")
        self._cursor.execute(sql.replace("%s", "?"), tuple(params))
        self.lastrowid = self._cursor.lastrowid
        self.rowcount = self._cursor.rowcount
        if self._cursor.description is not None:
            self._filas = self._cursor.fetchall()
            self._sin_leer = True
        else:
            self._filas = []

    def fetchone(self):
        if not self._filas:
            self._sin_leer = False
            return None
        fila = self._filas.pop(0)
        if not self._filas:
            self._sin_leer = False
        return self._empaquetar(fila)

    def fetchall(self):
        filas, self._filas = self._filas, []
        self._sin_leer = False
        return [self._empaquetar(fila) for fila in filas]

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
    resp = cliente.post("/api/login", json={"email": email, "password": "x"})
    assert resp.status_code == 200
    return resp


def test_usuario_autorizado_envia_tarea_a_revision(cliente, base):
    _login(cliente, "responsable@nahan.local")

    respuesta = cliente.put("/api/tareas/1/estado", json={"estado": "EN_REVISION"})

    assert respuesta.status_code == 200
    tarea = base.execute("SELECT estado FROM tarea WHERE id_tarea = 1").fetchone()
    assert tarea["estado"] == "EN_REVISION"
    registro = base.execute("SELECT * FROM revision_tarea WHERE id_tarea = 1").fetchone()
    assert registro is not None
    assert registro["accion"] == "ENVIO_REVISION"
    assert "estado_previo=EN_PROCESO" in (registro["observaciones"] or "")
    admin = base.execute("SELECT * FROM notificacion WHERE id_usuario = 1 ORDER BY id_notificacion DESC").fetchone()
    assert admin is not None
    assert "En revisión" in (admin["mensaje"] or "")


def test_el_admin_aprueba_una_tarea_en_revision(cliente, base):
    _login(cliente, "responsable@nahan.local")
    cliente.put("/api/tareas/1/estado", json={"estado": "EN_REVISION"})
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.put("/api/tareas/1/revision", json={"accion": "aprobar"})

    assert respuesta.status_code == 200
    tarea = base.execute("SELECT estado, fecha_finalizacion FROM tarea WHERE id_tarea = 1").fetchone()
    assert tarea["estado"] == "COMPLETADA"
    assert tarea["fecha_finalizacion"] is not None
    registro = base.execute("SELECT * FROM revision_tarea WHERE id_tarea = 1 ORDER BY id_revision DESC LIMIT 1").fetchone()
    assert registro["accion"] == "APROBAR_REVISION"
    evento = base.execute("SELECT * FROM auditoria WHERE accion = 'APROBAR_REVISION'").fetchone()
    assert evento is not None
    assert evento["id_usuario"] == 1


def test_el_admin_rechaza_una_tarea_en_revision_y_vuelve_al_estado_anterior(cliente, base):
    _login(cliente, "responsable@nahan.local")
    cliente.put("/api/tareas/1/estado", json={"estado": "EN_REVISION"})
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.put("/api/tareas/1/revision", json={"accion": "rechazar", "observaciones": "Faltan detalles"})

    assert respuesta.status_code == 200
    tarea = base.execute("SELECT estado, observaciones FROM tarea WHERE id_tarea = 1").fetchone()
    assert tarea["estado"] == "EN_PROCESO"
    assert "Faltan detalles" in (tarea["observaciones"] or "")
    registro = base.execute("SELECT * FROM revision_tarea WHERE id_tarea = 1 ORDER BY id_revision DESC LIMIT 1").fetchone()
    assert registro["accion"] == "RECHAZAR_REVISION"
    assert "Faltan detalles" in (registro["observaciones"] or "")


def test_usuario_normal_no_puede_aprobar_ni_rechazar(cliente, base):
    _login(cliente, "responsable@nahan.local")
    cliente.put("/api/tareas/1/estado", json={"estado": "EN_REVISION"})

    resp_aprobar = cliente.put("/api/tareas/1/revision", json={"accion": "aprobar"})
    resp_rechazar = cliente.put("/api/tareas/1/revision", json={"accion": "rechazar", "observaciones": "No"})

    assert resp_aprobar.status_code == 403
    assert resp_rechazar.status_code == 403


def test_no_se_puede_aprobar_ni_rechazar_sin_estar_en_revision(cliente, base):
    _login(cliente, "admin@nahan.local")

    assert cliente.put("/api/tareas/1/revision", json={"accion": "aprobar"}).status_code == 409
    assert cliente.put("/api/tareas/1/revision", json={"accion": "rechazar", "observaciones": "X"}).status_code == 409


def test_usuario_no_autorizado_no_puede_enviar_tarea_ajena_a_revision(cliente):
    _login(cliente, "ajeno@nahan.local")

    respuesta = cliente.put("/api/tareas/1/estado", json={"estado": "EN_REVISION"})

    assert respuesta.status_code == 403


def test_no_se_puede_enviar_repetidamente_una_tarea_ya_en_revision(cliente, base):
    _login(cliente, "responsable@nahan.local")
    cliente.put("/api/tareas/1/estado", json={"estado": "EN_REVISION"})

    respuesta = cliente.put("/api/tareas/1/estado", json={"estado": "EN_REVISION"})

    assert respuesta.status_code == 409


def test_rechazo_con_observaciones_vacias_rechaza_la_operacion(cliente, base):
    _login(cliente, "responsable@nahan.local")
    cliente.put("/api/tareas/1/estado", json={"estado": "EN_REVISION"})
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.put("/api/tareas/1/revision", json={"accion": "rechazar", "observaciones": "   "})

    assert respuesta.status_code == 400


def test_no_se_rechaza_si_no_hay_historial_de_envio_a_revision(cliente, base):
    _login(cliente, "admin@nahan.local")
    base.execute("UPDATE tarea SET estado = 'EN_REVISION' WHERE id_tarea = 1")
    base.commit()

    respuesta = cliente.put(
        "/api/tareas/1/revision",
        json={"accion": "rechazar", "observaciones": "Faltan datos"},
    )

    assert respuesta.status_code == 409
    assert "estado previo" in (respuesta.get_json()["error"] or "").lower()

    tarea = base.execute("SELECT estado FROM tarea WHERE id_tarea = 1").fetchone()
    assert tarea["estado"] == "EN_REVISION"
    assert base.execute("SELECT COUNT(*) AS n FROM revision_tarea WHERE id_tarea = 1").fetchone()["n"] == 0
    assert base.execute("SELECT COUNT(*) AS n FROM auditoria WHERE accion = 'RECHAZAR_REVISION'").fetchone()["n"] == 0


# --- Estabilización: resultado sin leer (H-01) y flujo eludible (H-02) ---

def _enviar_a_revision(cliente):
    _login(cliente, "responsable@nahan.local")
    respuesta = cliente.put("/api/tareas/1/estado", json={"estado": "EN_REVISION"})
    assert respuesta.status_code == 200


def test_el_cursor_de_prueba_detecta_resultados_sin_leer(base):
    cursor = _Conexion(base).cursor()
    cursor.execute("SELECT 1 FROM revision_tarea LIMIT 1")

    with pytest.raises(RuntimeError, match="Unread result found"):
        cursor.execute("SELECT 1")


def test_la_comprobacion_de_revision_tarea_consume_su_resultado(base):
    cursor = _Conexion(base).cursor(dictionary=True)

    assert tareas_routes._revision_tarea_disponible(cursor) is True
    # Con el resultado pendiente, esta sentencia fallaría en MySQL.
    cursor.execute("SELECT COUNT(*) AS n FROM revision_tarea")
    assert cursor.fetchone()["n"] == 0


@pytest.mark.parametrize("estado", ["EN_PROCESO", "PENDIENTE"])
def test_responsable_no_saca_la_tarea_de_revision_por_estado(cliente, base, estado):
    _enviar_a_revision(cliente)

    respuesta = cliente.put("/api/tareas/1/estado", json={"estado": estado})

    assert respuesta.status_code == 409
    assert "revisión" in respuesta.get_json()["error"]
    assert base.execute("SELECT estado FROM tarea WHERE id_tarea = 1").fetchone()["estado"] == "EN_REVISION"


@pytest.mark.parametrize("estado", ["COMPLETADA", "CANCELADA", "EN_PROCESO", "PENDIENTE"])
def test_administrador_no_saca_la_tarea_de_revision_por_estado(cliente, base, estado):
    _enviar_a_revision(cliente)
    _login(cliente, "admin@nahan.local")
    auditoria_antes = base.execute("SELECT COUNT(*) AS n FROM auditoria").fetchone()["n"]
    notificaciones_antes = base.execute("SELECT COUNT(*) AS n FROM notificacion").fetchone()["n"]

    respuesta = cliente.put("/api/tareas/1/estado", json={"estado": estado})

    assert respuesta.status_code == 409
    tarea = base.execute("SELECT estado, fecha_finalizacion FROM tarea WHERE id_tarea = 1").fetchone()
    assert tarea["estado"] == "EN_REVISION"
    assert tarea["fecha_finalizacion"] is None
    # El intento bloqueado no deja rastro: ni revisión, ni auditoría, ni aviso.
    assert base.execute("SELECT COUNT(*) AS n FROM revision_tarea").fetchone()["n"] == 1
    assert base.execute("SELECT COUNT(*) AS n FROM auditoria").fetchone()["n"] == auditoria_antes
    assert base.execute("SELECT COUNT(*) AS n FROM notificacion").fetchone()["n"] == notificaciones_antes


def test_el_envio_a_revision_audita_y_notifica_a_los_administradores(cliente, base):
    _enviar_a_revision(cliente)

    eventos = base.execute(
        "SELECT tabla_afectada, id_registro, id_usuario FROM auditoria "
        "WHERE accion = 'ENVIO_REVISION' ORDER BY id_auditoria"
    ).fetchall()
    id_revision = base.execute("SELECT id_revision FROM revision_tarea").fetchone()["id_revision"]
    assert [(e["tabla_afectada"], e["id_registro"], e["id_usuario"]) for e in eventos] == [
        ("tarea", 1, 2),
        ("revision_tarea", id_revision, 2),
    ]
    avisos = base.execute("SELECT id_usuario, tipo FROM notificacion").fetchall()
    assert [(a["id_usuario"], a["tipo"]) for a in avisos] == [(1, "REVISION_TAREA")]


def test_la_aprobacion_audita_y_notifica_al_responsable(cliente, base):
    _enviar_a_revision(cliente)
    _login(cliente, "admin@nahan.local")

    assert cliente.put("/api/tareas/1/revision", json={"accion": "aprobar"}).status_code == 200

    eventos = base.execute(
        "SELECT tabla_afectada, id_usuario, datos_nuevos FROM auditoria "
        "WHERE accion = 'APROBAR_REVISION' ORDER BY id_auditoria"
    ).fetchall()
    assert [e["tabla_afectada"] for e in eventos] == ["tarea", "revision_tarea"]
    assert all(e["id_usuario"] == 1 for e in eventos)
    assert "estado=COMPLETADA" in eventos[0]["datos_nuevos"]
    aviso = base.execute(
        "SELECT tipo, mensaje FROM notificacion WHERE id_usuario = 2 ORDER BY id_notificacion DESC"
    ).fetchone()
    assert aviso["tipo"] == "REVISION_TAREA"
    assert "aprobada" in aviso["mensaje"]


@pytest.mark.parametrize("estado_previo", ["PENDIENTE", "EN_PROCESO"])
def test_el_rechazo_restaura_el_estado_previo_audita_y_notifica(cliente, base, estado_previo):
    base.execute("UPDATE tarea SET estado = ? WHERE id_tarea = 1", (estado_previo,))
    base.commit()
    _enviar_a_revision(cliente)
    _login(cliente, "admin@nahan.local")

    respuesta = cliente.put(
        "/api/tareas/1/revision",
        json={"accion": "rechazar", "observaciones": "Falta el respaldo"},
    )

    assert respuesta.status_code == 200
    tarea = base.execute("SELECT estado, fecha_finalizacion FROM tarea WHERE id_tarea = 1").fetchone()
    assert tarea["estado"] == estado_previo
    assert tarea["fecha_finalizacion"] is None
    eventos = base.execute(
        "SELECT tabla_afectada, datos_nuevos FROM auditoria "
        "WHERE accion = 'RECHAZAR_REVISION' ORDER BY id_auditoria"
    ).fetchall()
    assert [e["tabla_afectada"] for e in eventos] == ["tarea", "revision_tarea"]
    assert f"estado={estado_previo}" in eventos[0]["datos_nuevos"]
    aviso = base.execute(
        "SELECT tipo, mensaje FROM notificacion WHERE id_usuario = 2 ORDER BY id_notificacion DESC"
    ).fetchone()
    assert aviso["tipo"] == "REVISION_TAREA"
    assert "rechazada" in aviso["mensaje"]
    assert "Falta el respaldo" in aviso["mensaje"]


def test_el_rechazo_sin_observaciones_no_modifica_la_tarea(cliente, base):
    _enviar_a_revision(cliente)
    _login(cliente, "admin@nahan.local")

    assert cliente.put("/api/tareas/1/revision", json={"accion": "rechazar"}).status_code == 400
    assert base.execute("SELECT estado FROM tarea WHERE id_tarea = 1").fetchone()["estado"] == "EN_REVISION"
    assert base.execute(
        "SELECT COUNT(*) AS n FROM revision_tarea WHERE accion = 'RECHAZAR_REVISION'"
    ).fetchone()["n"] == 0


def test_tras_el_rechazo_la_tarea_puede_volver_a_enviarse(cliente, base):
    _enviar_a_revision(cliente)
    _login(cliente, "admin@nahan.local")
    cliente.put("/api/tareas/1/revision", json={"accion": "rechazar", "observaciones": "Corregir"})

    _enviar_a_revision(cliente)

    assert base.execute("SELECT estado FROM tarea WHERE id_tarea = 1").fetchone()["estado"] == "EN_REVISION"
