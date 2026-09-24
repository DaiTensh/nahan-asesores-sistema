# -*- coding: utf-8 -*-
"""RF40 — Historiando Consolidadamente las Actividades.

GET /api/reportes/historial-consolidado consolida AUDITORIA dentro de un
período (filtrable por módulo y usuario), registra la generación en REPORTE y
se exporta a PDF y Excel con /api/reportes/<id>/pdf|excel. Solo administrador.
Corre sobre SQLite en memoria; la inserción en REPORTE se reemplaza porque
usa funciones propias de MySQL (DATE_FORMAT, LAST_INSERT_ID).
"""
import io
import json
import sqlite3

import pytest
from openpyxl import load_workbook

import backend.routes.auth_routes as auth_routes
import backend.routes.reportes_routes as reportes_routes
import backend.utils.auth as auth_utils
from backend.app import app as flask_app

ESQUEMA = """
CREATE TABLE rol (id_rol INTEGER PRIMARY KEY AUTOINCREMENT, nombre_rol TEXT);
CREATE TABLE area (id_area INTEGER PRIMARY KEY AUTOINCREMENT, nombre_area TEXT);
CREATE TABLE usuario (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT, id_rol INTEGER, id_area INTEGER,
    nombres TEXT, email TEXT UNIQUE, password_hash TEXT, estado TEXT DEFAULT 'ACTIVO');
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tabla_afectada TEXT, id_registro INTEGER, accion TEXT, datos_anteriores TEXT,
    datos_nuevos TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE reporte (
    id_reporte INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER, tipo_reporte TEXT,
    parametros TEXT, fecha_generacion DATETIME DEFAULT CURRENT_TIMESTAMP, archivo_url TEXT);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_JURIDICA');
INSERT INTO area (nombre_area) VALUES ('ADMINISTRACION'), ('JURIDICA');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) VALUES
 (1, 1, 'Admin Nahan', 'admin@nahan.local', 'hash'),
 (2, 2, 'Usuaria Juridica', 'juridica@nahan.local', 'hash');

INSERT INTO auditoria (id_usuario, tabla_afectada, id_registro, accion, datos_anteriores, datos_nuevos, fecha) VALUES
 (1, 'tarea',   5, 'EDICION',       'id_tarea=5, prioridad=MEDIA', 'id_tarea=5, prioridad=ALTA', '2026-09-01 10:00:00'),
 (2, 'tarea',   5, 'REASIGNACION',  'id_tarea=5, id_responsable=1', 'id_tarea=5, id_responsable=2', '2026-09-10 09:30:00'),
 (1, 'cliente', 3, 'CAMBIO_ESTADO', 'estado: ACTIVO', 'estado: INACTIVO', '2026-09-15 18:00:00'),
 (2, 'documento', 8, 'DESCARGA',    NULL, '=HYPERLINK("x")', '2026-10-20 12:00:00');
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

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


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


def _registrar_generacion_sqlite(cursor, id_usuario, tipo_reporte, parametros):
    cursor.execute(
        "INSERT INTO reporte (id_usuario, tipo_reporte, parametros) VALUES (%s, %s, %s)",
        (id_usuario, tipo_reporte, json.dumps(parametros)),
    )
    return {"id_reporte": cursor.lastrowid, "fecha_generacion": "24-09-2026 10:00"}


@pytest.fixture
def cliente(base, monkeypatch):
    conexion_falsa = lambda: _Conexion(base)

    monkeypatch.setattr(auth_routes, "get_connection", conexion_falsa)
    monkeypatch.setattr(auth_utils, "get_connection", conexion_falsa)
    monkeypatch.setattr(reportes_routes, "get_connection", conexion_falsa)
    monkeypatch.setattr(reportes_routes, "_registrar_generacion", _registrar_generacion_sqlite)

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as cliente_http:
        yield cliente_http


def _login(cliente, email):
    respuesta = cliente.post("/api/login", json={"email": email, "password": "x"})
    assert respuesta.status_code == 200


URL = "/api/reportes/historial-consolidado"


def test_consolida_el_periodo_en_orden_cronologico_y_registra_la_generacion(cliente, base):
    _login(cliente, "admin@nahan.local")

    datos = cliente.get(f"{URL}?fecha_inicio=2026-09-01&fecha_fin=2026-09-30").get_json()

    assert datos["total"] == 3
    assert [e["accion"] for e in datos["eventos"]] == ["CAMBIO_ESTADO", "REASIGNACION", "EDICION"]
    assert datos["resumen_por_modulo"] == {"Clientes": 1, "Tareas": 2}
    assert datos["id_reporte"] is not None
    fila = base.execute("SELECT tipo_reporte, parametros FROM reporte").fetchone()
    assert fila["tipo_reporte"] == "HISTORIAL_CONSOLIDADO"
    assert json.loads(fila["parametros"])["fecha_fin"] == "2026-09-30"


def test_filtra_por_modulo_y_usuario(cliente):
    _login(cliente, "admin@nahan.local")

    datos = cliente.get(
        f"{URL}?fecha_inicio=2026-09-01&fecha_fin=2026-10-31&modulo=Tareas&id_usuario=2"
    ).get_json()

    assert [e["accion"] for e in datos["eventos"]] == ["REASIGNACION"]
    assert datos["filtros"]["usuario"]["nombres"] == "Usuaria Juridica"


def test_sin_actividades_no_registra_la_generacion(cliente, base):
    _login(cliente, "admin@nahan.local")

    datos = cliente.get(f"{URL}?fecha_inicio=2026-01-01&fecha_fin=2026-01-31").get_json()

    assert datos["eventos"] == [] and datos["id_reporte"] is None
    assert datos["mensaje"] == reportes_routes.MENSAJE_SIN_ACTIVIDADES
    assert base.execute("SELECT COUNT(*) FROM reporte").fetchone()[0] == 0


def test_valida_periodo_modulo_y_usuario(cliente):
    _login(cliente, "admin@nahan.local")

    assert cliente.get(URL).status_code == 400
    assert cliente.get(f"{URL}?fecha_inicio=2026-09-30&fecha_fin=2026-09-01").status_code == 400
    assert cliente.get(f"{URL}?fecha_inicio=2026-09-01&fecha_fin=2026-09-30&modulo=X").status_code == 400
    assert cliente.get(f"{URL}?fecha_inicio=2026-09-01&fecha_fin=2026-09-30&id_usuario=99").status_code == 404


def test_solo_administrador(cliente):
    _login(cliente, "juridica@nahan.local")

    assert cliente.get(f"{URL}?fecha_inicio=2026-09-01&fecha_fin=2026-09-30").status_code == 403


def test_exporta_a_excel_con_encabezados_y_sin_formulas(cliente):
    _login(cliente, "admin@nahan.local")
    id_reporte = cliente.get(f"{URL}?fecha_inicio=2026-09-01&fecha_fin=2026-10-31").get_json()["id_reporte"]

    respuesta = cliente.get(f"/api/reportes/{id_reporte}/excel")

    assert respuesta.status_code == 200
    assert "historial_consolidado_todos_los_modulos_2026-09-01_a_2026-10-31.xlsx" in respuesta.headers["Content-Disposition"]
    hoja = load_workbook(io.BytesIO(respuesta.data)).active
    filas = list(hoja.values)
    assert filas[0] == ("Fecha y hora", "Usuario", "Módulo", "Acción", "Registro", "Antes", "Después")
    assert len(filas) == 5
    assert hoja["G2"].data_type == "s"


def test_exporta_a_pdf(cliente):
    _login(cliente, "admin@nahan.local")
    id_reporte = cliente.get(f"{URL}?fecha_inicio=2026-09-01&fecha_fin=2026-09-30").get_json()["id_reporte"]

    respuesta = cliente.get(f"/api/reportes/{id_reporte}/pdf")

    assert respuesta.status_code == 200
    assert respuesta.data[:4] == b"%PDF"
