import sqlite3
from pathlib import Path

import pytest

import backend.routes.auth_routes as auth_routes
import backend.routes.historial_routes as historial_routes
import backend.utils.auth as auth_utils
from backend.app import app as flask_app
from backend.utils.security import hash_password

RAIZ = Path(__file__).resolve().parents[1]


class Cursor:
    def __init__(self, connection, dictionary):
        self.cursor = connection.cursor()
        self.dictionary = dictionary

    def execute(self, sql, params=()):
        self.cursor.execute(sql.replace("%s", "?"), tuple(params))

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row is not None and self.dictionary else row

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [dict(row) for row in rows] if self.dictionary else rows

    def close(self):
        self.cursor.close()


class Connection:
    def __init__(self, database):
        self.database = database

    def cursor(self, dictionary=False):
        return Cursor(self.database, dictionary)

    def commit(self):
        self.database.commit()

    def rollback(self):
        self.database.rollback()

    def close(self):
        pass


@pytest.fixture
def cliente_rf49(monkeypatch):
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.executescript(
        """
        CREATE TABLE rol (id_rol INTEGER PRIMARY KEY, nombre_rol TEXT);
        CREATE TABLE area (id_area INTEGER PRIMARY KEY, nombre_area TEXT);
        CREATE TABLE usuario (
            id_usuario INTEGER PRIMARY KEY, id_rol INTEGER, id_area INTEGER,
            nombres TEXT, email TEXT, password_hash TEXT, estado TEXT,
            debe_cambiar_password INTEGER DEFAULT 0, version_credenciales INTEGER DEFAULT 0
        );
        CREATE TABLE cliente (id_cliente INTEGER PRIMARY KEY);
        CREATE TABLE tarea (id_tarea INTEGER PRIMARY KEY);
        CREATE TABLE auditoria (
            id_auditoria INTEGER PRIMARY KEY, id_usuario INTEGER,
            tabla_afectada TEXT, id_registro INTEGER, accion TEXT,
            datos_anteriores TEXT, datos_nuevos TEXT, fecha DATETIME
        );
        INSERT INTO rol VALUES (1, 'ADMINISTRADOR'), (2, 'USUARIO_AREA_JURIDICA');
        INSERT INTO area VALUES (1, 'ADMINISTRACION'), (2, 'JURIDICA');
        """
    )
    database.executemany(
        "INSERT INTO usuario (id_usuario, id_rol, id_area, nombres, email, password_hash, estado) "
        "VALUES (?, ?, ?, ?, ?, ?, 'ACTIVO')",
        [
            (1, 1, 1, "Admin RF49", "admin@nahan.local", hash_password("x")),
            (2, 2, 2, "Usuario RF49", "usuario@nahan.local", hash_password("x")),
        ],
    )
    database.execute("INSERT INTO cliente VALUES (201)")
    database.execute("INSERT INTO tarea VALUES (101)")
    filas = []
    for id_evento in range(1, 13):
        tabla, id_registro, accion = "sesion", 1, "LOGIN"
        if id_evento == 12:
            tabla, id_registro, accion = "tarea", 101, "TAREA_MODIFICADA"
        elif id_evento == 11:
            tabla, id_registro, accion = "cliente", 201, "CLIENTE_MODIFICADO"
        elif id_evento == 10:
            tabla, id_registro, accion = "tarea", 999, "TAREA_MODIFICADA"
        elif id_evento == 9:
            tabla, id_registro, accion = "observacion_cliente", 55, "OBSERVACION_CREADA"
        filas.append((
            id_evento,
            1 if id_evento % 2 == 0 else 2,
            tabla,
            id_registro,
            accion,
            "dato privado anterior",
            "dato privado nuevo",
            f"2026-10-{id_evento:02d} 10:11:12",
        ))
    database.executemany(
        """
        INSERT INTO auditoria
            (id_auditoria, id_usuario, tabla_afectada, id_registro, accion,
             datos_anteriores, datos_nuevos, fecha)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        filas,
    )
    database.commit()

    connection_factory = lambda: Connection(database)
    monkeypatch.setattr(auth_routes, "get_connection", connection_factory)
    monkeypatch.setattr(auth_utils, "get_connection", connection_factory)
    monkeypatch.setattr(historial_routes, "get_connection", connection_factory)
    monkeypatch.setattr(auth_routes, "registrar_auditoria", lambda *args, **kwargs: None)
    flask_app.config["TESTING"] = True

    with flask_app.test_client() as client:
        yield client, database
    database.close()


def iniciar_sesion(client, email):
    respuesta = client.post("/api/login", json={"email": email, "password": "x"})
    assert respuesta.status_code == 200


def test_rf49_administrador_ve_cambios_reales_limitados_y_ordenados(cliente_rf49):
    client, _ = cliente_rf49
    iniciar_sesion(client, "admin@nahan.local")

    respuesta = client.get("/api/cambios-recientes")
    data = respuesta.get_json()

    assert respuesta.status_code == 200
    assert data["limite"] == 10
    assert len(data["cambios"]) == 10
    assert [evento["id_auditoria"] for evento in data["cambios"]] == list(range(12, 2, -1))
    assert {"tipo", "modulo", "fecha", "hora", "usuario"} <= set(data["cambios"][0])
    assert "datos_anteriores" not in data["cambios"][0]
    assert "datos_nuevos" not in data["cambios"][0]


def test_rf49_requiere_administrador_en_ambos_endpoints(cliente_rf49):
    client, _ = cliente_rf49
    assert client.get("/api/cambios-recientes").status_code == 401
    assert client.get("/api/cambios-recientes/filtros").status_code == 401

    iniciar_sesion(client, "usuario@nahan.local")
    assert client.get("/api/cambios-recientes").status_code == 403
    assert client.get("/api/cambios-recientes/filtros").status_code == 403


def test_rf49_filtra_por_modulo_tipo_y_combinacion(cliente_rf49):
    client, _ = cliente_rf49
    iniciar_sesion(client, "admin@nahan.local")

    modulo = client.get("/api/cambios-recientes?modulo=Clientes").get_json()["cambios"]
    tipo = client.get("/api/cambios-recientes?accion=CLIENTE_MODIFICADO").get_json()["cambios"]
    ambos = client.get(
        "/api/cambios-recientes?modulo=Clientes&accion=CLIENTE_MODIFICADO"
    ).get_json()["cambios"]

    assert all(evento["modulo"] == "Clientes" for evento in modulo)
    assert all(evento["tipo"] == "CLIENTE_MODIFICADO" for evento in tipo)
    assert [evento["id_auditoria"] for evento in ambos] == [11]


def test_rf49_filtros_son_dinamicos_y_parametros_invalidos_se_rechazan(cliente_rf49):
    client, _ = cliente_rf49
    iniciar_sesion(client, "admin@nahan.local")

    filtros = client.get("/api/cambios-recientes/filtros").get_json()
    assert "Clientes" in filtros["modulos"]
    assert "TAREA_MODIFICADA" in filtros["tipos"]
    assert client.get("/api/cambios-recientes?modulo=Inexistente").status_code == 400
    assert client.get("/api/cambios-recientes?accion=LOGIN%27%20OR%201%3D1").status_code == 400


def test_rf49_enlaza_solo_registros_existentes_y_compatibles(cliente_rf49):
    client, _ = cliente_rf49
    iniciar_sesion(client, "admin@nahan.local")

    cambios = client.get("/api/cambios-recientes").get_json()["cambios"]
    por_id = {evento["id_auditoria"]: evento for evento in cambios}

    assert (por_id[12]["tipo_registro"], por_id[12]["id_registro"]) == ("tarea", 101)
    assert (por_id[11]["tipo_registro"], por_id[11]["id_registro"]) == ("cliente", 201)
    assert por_id[10]["tipo_registro"] is None
    assert por_id[10]["id_registro"] is None
    assert por_id[9]["tipo_registro"] is None


def test_rf49_sin_cambios_devuelve_lista_vacia(cliente_rf49):
    client, database = cliente_rf49
    iniciar_sesion(client, "admin@nahan.local")
    database.execute("DELETE FROM auditoria")
    database.commit()

    respuesta = client.get("/api/cambios-recientes")

    assert respuesta.status_code == 200
    assert respuesta.get_json()["cambios"] == []


def test_rf49_tipo_valido_sin_coincidencias_devuelve_lista_vacia(cliente_rf49):
    client, _ = cliente_rf49
    iniciar_sesion(client, "admin@nahan.local")

    respuesta = client.get("/api/cambios-recientes?accion=CLIENTE_CREADO")

    assert respuesta.status_code == 200
    assert respuesta.get_json()["cambios"] == []


def test_rf49_dashboard_incluye_filtros_y_un_solo_refresco_automatico():
    html = (RAIZ / "frontend/dashboard/dashboard.html").read_text(encoding="utf-8")
    script = (RAIZ / "frontend/dashboard/cambios_recientes.js").read_text(encoding="utf-8")

    assert 'src="./cambios_recientes.js"' in html
    assert 'id="filtroModuloCambios"' in html
    assert 'id="filtroTipoCambio"' in html
    assert script.count("window.setInterval(") == 1
    assert "INTERVALO_ACTUALIZACION_MS = 30000" in script
    assert 'window.addEventListener("pagehide", detenerTemporizador)' in script
    assert 'window.addEventListener("pageshow"' in script
    assert 'parametros.set("modulo", modulo)' in script
    assert 'parametros.set("accion", accion)' in script