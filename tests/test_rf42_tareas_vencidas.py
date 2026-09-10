# -*- coding: utf-8 -*-
"""RF42 — Visualizando Tareas Vencidas.

GET /api/tareas/vencidas usa CURDATE()/DATEDIFF (funciones específicas de
MySQL), así que corre con el mismo patrón de `fake_connection_factory` que
test_rf39_productividad_por_usuario.py, no con SQLite real: el mock no
evalúa fechas, solo devuelve filas ya armadas y deja verificar qué condición
y qué parámetros armó la ruta según el rol.
"""
from tests.conftest import normalize_sql

import backend.routes.tareas_routes as tareas_routes


def _handler(tareas):
    def handler(sql, params, cursor):
        sql_normalizado = normalize_sql(sql)
        if "FROM tarea t" in sql_normalizado and "dias_retraso" in sql_normalizado:
            return [f.copy() for f in tareas]
        return []
    return handler


def test_devuelve_cliente_responsable_y_dias_de_retraso(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=2, rol_id=1)

    tareas = [{
        "id_tarea": 1, "titulo": "Tarea vencida", "estado": "EN_PROCESO",
        "prioridad": "URGENTE", "fecha_vencimiento": "2026-09-01",
        "cliente": "Cliente X", "responsable": "Fulano", "dias_retraso": 5,
    }]
    connection = fake_connection_factory(_handler(tareas))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    respuesta = client.get("/api/tareas/vencidas")
    data = respuesta.get_json()

    assert respuesta.status_code == 200
    assert data[0]["cliente"] == "Cliente X"
    assert data[0]["responsable"] == "Fulano"
    assert data[0]["dias_retraso"] == 5


def test_administrador_ve_las_de_todos(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    connection = fake_connection_factory(_handler([]))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    client.get("/api/tareas/vencidas")

    sql, params = connection.executed[-1]
    assert "t.id_responsable = %s" not in normalize_sql(sql)
    # Solo los estados finales van como parámetro; no hay filtro por usuario.
    assert set(params) == tareas_routes.ESTADOS_FINALES


def test_usuario_no_administrador_solo_ve_las_propias(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=7, rol_id=2)

    connection = fake_connection_factory(_handler([]))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    client.get("/api/tareas/vencidas")

    sql, params = connection.executed[-1]
    assert "t.id_responsable = %s" in normalize_sql(sql)
    assert params[-1] == 7


def test_excluye_completadas_y_canceladas_del_filtro_de_estado(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    connection = fake_connection_factory(_handler([]))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    client.get("/api/tareas/vencidas")

    sql, params = connection.executed[-1]
    assert "NOT IN" in normalize_sql(sql)
    assert "COMPLETADA" in params
    assert "CANCELADA" in params
