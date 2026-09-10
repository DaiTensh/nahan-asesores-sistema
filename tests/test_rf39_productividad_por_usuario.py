# -*- coding: utf-8 -*-
"""RF39 — Visualizando la Productividad por Usuario.

GET /api/reportes/productividad devuelve, por usuario activo: tareas
completadas dentro del período, tiempo promedio de resolución (entre
fecha_creacion y fecha_finalizacion) y carga vigente (PENDIENTE/EN_PROCESO,
sin filtrar por período). Solo ADMINISTRADOR.

El módulo de reportes usa funciones específicas de MySQL (DATE_FORMAT,
DATE_ADD ... INTERVAL), así que estas pruebas corren con el mismo patrón de
`fake_connection_factory` que test_incremento1_regression.py, no con SQLite
real.
"""
from tests.conftest import normalize_sql

import backend.routes.reportes_routes as reportes_routes


def _handler(usuarios, completadas, carga, area_valida=True):
    def handler(sql, params, cursor):
        sql_normalizado = normalize_sql(sql)

        if "SELECT id_area FROM area WHERE id_area" in sql_normalizado:
            return [{"id_area": params[0]}] if area_valida else []

        if "SELECT id_usuario, nombres, id_area FROM usuario" in sql_normalizado:
            return [u.copy() for u in usuarios]

        if "SELECT id_responsable, fecha_creacion, fecha_finalizacion FROM tarea" in sql_normalizado:
            return [f.copy() for f in completadas]

        if "SELECT id_responsable, COUNT(*) AS total FROM tarea" in sql_normalizado:
            return [f.copy() for f in carga]

        if "SELECT DATE_FORMAT(fecha_generacion" in sql_normalizado:
            return [{"fecha_generacion": "10-09-2026 12:00"}]

        return []

    return handler


def _autorizar(client, monkeypatch, iniciar_sesion, rol_id=1):
    iniciar_sesion(usuario_id=1, rol_id=rol_id, area_id=1)


def test_solo_administrador_puede_acceder(client, iniciar_sesion):
    _autorizar(client, None, iniciar_sesion, rol_id=2)

    respuesta = client.get(
        "/api/reportes/productividad?fecha_inicio=2026-01-01&fecha_fin=2026-01-31"
    )

    assert respuesta.status_code == 403


def test_requiere_fechas(client, iniciar_sesion):
    _autorizar(client, None, iniciar_sesion)

    respuesta = client.get("/api/reportes/productividad")

    assert respuesta.status_code == 400


def test_cuenta_completadas_y_calcula_tiempo_promedio(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    _autorizar(client, None, iniciar_sesion)

    usuarios = [{"id_usuario": 2, "nombres": "Ivan Gomez", "id_area": 2}]
    completadas = [
        {
            "id_responsable": 2,
            "fecha_creacion": "2026-01-05 09:00:00",
            "fecha_finalizacion": "2026-01-05 11:00:00",
        },
        {
            "id_responsable": 2,
            "fecha_creacion": "2026-01-06 09:00:00",
            "fecha_finalizacion": "2026-01-06 15:00:00",
        },
    ]
    carga = [{"id_responsable": 2, "total": 3}]

    connection = fake_connection_factory(_handler(usuarios, completadas, carga))
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: connection)

    respuesta = client.get(
        "/api/reportes/productividad?fecha_inicio=2026-01-01&fecha_fin=2026-01-31"
    )
    data = respuesta.get_json()

    assert respuesta.status_code == 200
    fila = data["usuarios"][0]
    assert fila["id_usuario"] == 2
    assert fila["tareas_completadas"] == 2
    # Promedio de 2h y 6h -> 4h.
    assert fila["tiempo_promedio_resolucion_horas"] == 4.0
    assert fila["carga_vigente"] == 3


def test_usuario_sin_completadas_no_tiene_promedio(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    _autorizar(client, None, iniciar_sesion)

    usuarios = [{"id_usuario": 5, "nombres": "Sin Tareas", "id_area": 2}]
    connection = fake_connection_factory(_handler(usuarios, [], []))
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: connection)

    respuesta = client.get(
        "/api/reportes/productividad?fecha_inicio=2026-01-01&fecha_fin=2026-01-31"
    )
    data = respuesta.get_json()

    fila = data["usuarios"][0]
    assert fila["tareas_completadas"] == 0
    assert fila["tiempo_promedio_resolucion_horas"] is None
    assert fila["carga_vigente"] == 0


def test_ordena_de_mayor_a_menor_por_completadas(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    _autorizar(client, None, iniciar_sesion)

    usuarios = [
        {"id_usuario": 2, "nombres": "Menos Productivo", "id_area": 2},
        {"id_usuario": 3, "nombres": "Mas Productivo", "id_area": 2},
    ]
    completadas = [
        {"id_responsable": 2, "fecha_creacion": "2026-01-01 09:00:00", "fecha_finalizacion": "2026-01-01 10:00:00"},
        {"id_responsable": 3, "fecha_creacion": "2026-01-01 09:00:00", "fecha_finalizacion": "2026-01-01 10:00:00"},
        {"id_responsable": 3, "fecha_creacion": "2026-01-02 09:00:00", "fecha_finalizacion": "2026-01-02 10:00:00"},
    ]
    connection = fake_connection_factory(_handler(usuarios, completadas, []))
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: connection)

    respuesta = client.get(
        "/api/reportes/productividad?fecha_inicio=2026-01-01&fecha_fin=2026-01-31"
    )
    data = respuesta.get_json()

    assert [fila["id_usuario"] for fila in data["usuarios"]] == [3, 2]


def test_area_inexistente_responde_404(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    _autorizar(client, None, iniciar_sesion)

    connection = fake_connection_factory(_handler([], [], [], area_valida=False))
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: connection)

    respuesta = client.get(
        "/api/reportes/productividad?fecha_inicio=2026-01-01&fecha_fin=2026-01-31&id_area=99"
    )

    assert respuesta.status_code == 404
