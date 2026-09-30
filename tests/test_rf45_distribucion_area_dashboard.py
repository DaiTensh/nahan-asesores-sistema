import sqlite3
from pathlib import Path

import pytest

from tests.conftest import normalize_sql

import backend.routes.reportes_routes as reportes_routes
from backend.utils import auth as auth_module

URL = "/api/reportes/distribucion-por-area"
ROOT_DIR = Path(__file__).resolve().parents[1]


def _handler(areas, clientes_por_area, tareas_por_area, total_clientes):
    def handler(sql, params, cursor):
        consulta = normalize_sql(sql)
        if "SELECT id_area, nombre_area FROM area" in consulta:
            return [area.copy() for area in areas]
        if "COUNT(DISTINCT id_cliente) AS total FROM cliente_area" in consulta and "GROUP BY" in consulta:
            return [fila.copy() for fila in clientes_por_area]
        if "COUNT(DISTINCT id_cliente) AS total FROM cliente_area" in consulta:
            return [{"total": total_clientes}]
        if "FROM tarea" in consulta and "GROUP BY id_area" in consulta:
            return [fila.copy() for fila in tareas_por_area]
        return []

    return handler


def _preparar(
    monkeypatch,
    iniciar_sesion,
    fake_connection_factory,
    areas=None,
    clientes_por_area=None,
    tareas_por_area=None,
    total_clientes=0,
    rol_id=1,
):
    iniciar_sesion(usuario_id=9, rol_id=rol_id)
    conexion = fake_connection_factory(
        _handler(
            areas or [],
            clientes_por_area or [],
            tareas_por_area or [],
            total_clientes,
        )
    )
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: conexion)
    return conexion


def test_distribuye_clientes_y_tareas_con_areas_dinamicas_y_proporciones(
    client, monkeypatch, iniciar_sesion, fake_connection_factory
):
    areas = [
        {"id_area": 12, "nombre_area": "AREA NUEVA"},
        {"id_area": 4, "nombre_area": "CONTABLE"},
        {"id_area": 9, "nombre_area": "JURIDICA"},
        {"id_area": 15, "nombre_area": "AREA SIN TAREAS"},
    ]
    conexion = _preparar(
        monkeypatch,
        iniciar_sesion,
        fake_connection_factory,
        areas=areas,
        clientes_por_area=[{"id_area": 4, "total": 2}, {"id_area": 9, "total": 2}, {"id_area": 15, "total": 1}],
        tareas_por_area=[{"id_area": 4, "total": 1}, {"id_area": 9, "total": 4}],
        total_clientes=3,
    )

    respuesta = client.get(URL)
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["total_clientes"] == 3
    assert datos["total_asignaciones_cliente_area"] == 5
    assert datos["total_tareas"] == 5
    assert datos["areas"] == [
        {"id_area": 12, "nombre_area": "AREA NUEVA", "clientes": 0, "porcentaje_clientes": 0.0, "tareas": 0, "porcentaje_tareas": 0.0},
        {"id_area": 4, "nombre_area": "CONTABLE", "clientes": 2, "porcentaje_clientes": 40.0, "tareas": 1, "porcentaje_tareas": 20.0},
        {"id_area": 9, "nombre_area": "JURIDICA", "clientes": 2, "porcentaje_clientes": 40.0, "tareas": 4, "porcentaje_tareas": 80.0},
        {"id_area": 15, "nombre_area": "AREA SIN TAREAS", "clientes": 1, "porcentaje_clientes": 20.0, "tareas": 0, "porcentaje_tareas": 0.0},
    ]

    sql_clientes = next(sql for sql, _ in conexion.executed if "FROM cliente_area" in normalize_sql(sql))
    sql_tareas = next(sql for sql, _ in conexion.executed if "FROM tarea" in normalize_sql(sql))
    sql_areas = next(sql for sql, _ in conexion.executed if "FROM area" in normalize_sql(sql))
    assert "COUNT(DISTINCT id_cliente)" in normalize_sql(sql_clientes)
    assert "estado" not in normalize_sql(sql_clientes)
    # Documento 0, Tabla 7.45: «Muestra distribución de tareas activas por
    # área». La consulta de tareas sí debe filtrar por estado.
    assert "WHERE estado IN (%s, %s, %s)" in normalize_sql(sql_tareas)
    assert "estado" not in normalize_sql(sql_areas)


def test_responde_todas_las_areas_con_cero_y_totales_cero_si_no_hay_datos(
    client, monkeypatch, iniciar_sesion, fake_connection_factory
):
    _preparar(
        monkeypatch,
        iniciar_sesion,
        fake_connection_factory,
        areas=[{"id_area": 31, "nombre_area": "AREA VACIA"}],
    )

    respuesta = client.get(URL)
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["total_clientes"] == 0
    assert datos["total_asignaciones_cliente_area"] == 0
    assert datos["total_tareas"] == 0
    assert datos["areas"] == [
        {"id_area": 31, "nombre_area": "AREA VACIA", "clientes": 0, "porcentaje_clientes": 0.0, "tareas": 0, "porcentaje_tareas": 0.0}
    ]


def test_sin_areas_devuelve_resumen_vacio(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    _preparar(monkeypatch, iniciar_sesion, fake_connection_factory)

    respuesta = client.get(URL)

    assert respuesta.status_code == 200
    assert respuesta.get_json() == {
        "areas": [],
        "total_clientes": 0,
        "total_asignaciones_cliente_area": 0,
        "total_tareas": 0,
    }


def test_solo_administrador_puede_consultar_distribucion(
    client, monkeypatch, iniciar_sesion, fake_connection_factory
):
    conexion = _preparar(
        monkeypatch,
        iniciar_sesion,
        fake_connection_factory,
        areas=[{"id_area": 12, "nombre_area": "AREA NUEVA"}],
        rol_id=2,
    )

    respuesta = client.get(URL)

    assert respuesta.status_code == 403
    assert conexion.executed == []


def test_dashboard_integra_la_distribucion_y_los_graficos_dinamicos():
    html = (ROOT_DIR / "frontend/dashboard/dashboard.html").read_text(encoding="utf-8")
    javascript = (ROOT_DIR / "frontend/dashboard/dashboard.js").read_text(encoding="utf-8")
    css = (ROOT_DIR / "frontend/dashboard/dashboard.css").read_text(encoding="utf-8")

    assert 'id="distribucionClientesPorArea"' in html
    assert 'id="distribucionTareasPorArea"' in html
    assert 'id="totalClientesDistribucionArea"' in html
    assert 'id="totalRelacionesClientesArea"' in html
    assert 'id="totalTareasDistribucionArea"' in html
    assert "cargarDistribucionPorArea();" in javascript
    assert '`${API_URL}/reportes/distribucion-por-area`' in javascript
    assert "dashboard-area-fill" in javascript
    assert ".dashboard-area-fill" in css


def test_supervisor_no_se_simula_con_roles_existentes():
    """El sistema no define un rol supervisor; no se equipara a roles de área."""
    assert all("SUPERVISOR" not in nombre for nombre in auth_module.ROLES.values())


# --- Estabilización: solo tareas activas (Documento 0, Tabla 7.45) ---

ESQUEMA_ACTIVAS = """
CREATE TABLE area (id_area INTEGER PRIMARY KEY, nombre_area TEXT);
CREATE TABLE cliente_area (id_cliente INTEGER, id_area INTEGER);
CREATE TABLE tarea (id_tarea INTEGER PRIMARY KEY AUTOINCREMENT, id_area INTEGER, estado TEXT);
INSERT INTO area VALUES (1, 'JURIDICA'), (2, 'CONTABLE'), (3, 'ADMINISTRACION');
INSERT INTO cliente_area VALUES (1, 1), (2, 1), (2, 2);
INSERT INTO tarea (id_area, estado) VALUES
  (1, 'PENDIENTE'), (1, 'EN_PROCESO'), (1, 'EN_REVISION'), (1, 'COMPLETADA'), (1, 'CANCELADA'),
  (2, 'PENDIENTE'), (2, 'COMPLETADA'), (2, 'COMPLETADA'), (2, 'CANCELADA'),
  (3, 'COMPLETADA'), (3, 'CANCELADA');
"""


class _CursorSqlite:
    def __init__(self, conexion):
        self._cursor = conexion.cursor()

    def execute(self, sql, params=()):
        self._cursor.execute(sql.replace("%s", "?"), tuple(params))

    def fetchone(self):
        fila = self._cursor.fetchone()
        return dict(fila) if fila is not None else None

    def fetchall(self):
        return [dict(fila) for fila in self._cursor.fetchall()]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _ConexionSqlite:
    def __init__(self, conexion):
        self._conexion = conexion

    def cursor(self, dictionary=False):
        return _CursorSqlite(self._conexion)

    def close(self):
        pass


@pytest.fixture
def base_activas(monkeypatch, iniciar_sesion):
    conexion = sqlite3.connect(":memory:")
    conexion.row_factory = sqlite3.Row
    conexion.executescript(ESQUEMA_ACTIVAS)
    iniciar_sesion(usuario_id=9, rol_id=1)
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: _ConexionSqlite(conexion))
    yield conexion
    conexion.close()


def _por_area(datos):
    return {area["nombre_area"]: area for area in datos["areas"]}


def test_cuenta_solo_tareas_activas_por_area(client, base_activas):
    datos = client.get(URL).get_json()
    areas = _por_area(datos)

    # 11 tareas en la base: 4 activas, 4 completadas y 3 canceladas.
    assert datos["total_tareas"] == 4
    assert areas["JURIDICA"]["tareas"] == 3
    assert areas["CONTABLE"]["tareas"] == 1
    assert areas["ADMINISTRACION"]["tareas"] == 0


def test_porcentajes_se_calculan_sobre_las_tareas_activas(client, base_activas):
    areas = _por_area(client.get(URL).get_json())

    assert areas["JURIDICA"]["porcentaje_tareas"] == 75.0
    assert areas["CONTABLE"]["porcentaje_tareas"] == 25.0
    assert areas["ADMINISTRACION"]["porcentaje_tareas"] == 0.0


@pytest.mark.parametrize("estado", ["COMPLETADA", "CANCELADA"])
def test_excluye_las_tareas_en_estado_final(client, base_activas, estado):
    antes = client.get(URL).get_json()
    base_activas.execute("INSERT INTO tarea (id_area, estado) VALUES (2, ?)", (estado,))
    base_activas.commit()

    assert client.get(URL).get_json() == antes


@pytest.mark.parametrize("estado", ["PENDIENTE", "EN_PROCESO", "EN_REVISION"])
def test_incluye_cada_estado_activo(client, base_activas, estado):
    base_activas.execute("INSERT INTO tarea (id_area, estado) VALUES (3, ?)", (estado,))
    base_activas.commit()

    datos = client.get(URL).get_json()

    assert datos["total_tareas"] == 5
    assert _por_area(datos)["ADMINISTRACION"]["tareas"] == 1


def test_un_area_solo_con_tareas_finales_queda_en_cero_sin_error(client, base_activas):
    base_activas.execute("DELETE FROM tarea WHERE estado IN ('PENDIENTE', 'EN_PROCESO', 'EN_REVISION')")
    base_activas.commit()

    datos = client.get(URL).get_json()

    assert datos["total_tareas"] == 0
    assert all(area["tareas"] == 0 and area["porcentaje_tareas"] == 0.0 for area in datos["areas"])


def test_la_distribucion_de_clientes_no_depende_del_estado_de_las_tareas(client, base_activas):
    datos = client.get(URL).get_json()
    areas = _por_area(datos)

    assert datos["total_clientes"] == 2
    assert datos["total_asignaciones_cliente_area"] == 3
    assert areas["JURIDICA"]["clientes"] == 2
    assert areas["CONTABLE"]["clientes"] == 1
