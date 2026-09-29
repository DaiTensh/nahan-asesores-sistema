from pathlib import Path

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
    assert "estado" not in normalize_sql(sql_tareas)
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
