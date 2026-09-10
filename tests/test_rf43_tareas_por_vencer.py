# -*- coding: utf-8 -*-
"""RF43 — Visualizando Tareas Próximas a Vencer.

GET /api/tareas/por-vencer?dias=<n>. Igual que RF42, corre con
`fake_connection_factory`: DATE_ADD/CURDATE no los evalúa SQLite.
"""
from tests.conftest import normalize_sql

import backend.routes.tareas_routes as tareas_routes


def _handler(tareas):
    def handler(sql, params, cursor):
        sql_normalizado = normalize_sql(sql)
        if "FROM tarea t" in sql_normalizado and "dias_restantes" in sql_normalizado:
            return [f.copy() for f in tareas]
        return []
    return handler


def test_dias_es_configurable_no_fijo(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    connection = fake_connection_factory(_handler([]))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    client.get("/api/tareas/por-vencer?dias=15")

    sql, params = connection.executed[-1]
    # dias + 1 días como límite superior exclusivo (ver comentario en la ruta).
    assert 16 in params


def test_dias_por_defecto_es_siete(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    connection = fake_connection_factory(_handler([]))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    client.get("/api/tareas/por-vencer")

    sql, params = connection.executed[-1]
    assert 8 in params


def test_dias_no_numerico_responde_400(client, iniciar_sesion):
    iniciar_sesion(usuario_id=1, rol_id=1)

    respuesta = client.get("/api/tareas/por-vencer?dias=abc")

    assert respuesta.status_code == 400


def test_dias_cero_o_negativo_responde_400(client, iniciar_sesion):
    iniciar_sesion(usuario_id=1, rol_id=1)

    respuesta = client.get("/api/tareas/por-vencer?dias=0")

    assert respuesta.status_code == 400


def test_usuario_no_administrador_solo_ve_las_propias(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=9, rol_id=2)

    connection = fake_connection_factory(_handler([]))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    client.get("/api/tareas/por-vencer")

    sql, params = connection.executed[-1]
    assert "t.id_responsable = %s" in normalize_sql(sql)
    assert params[-1] == 9


def test_devuelve_dias_restantes(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    tareas = [{
        "id_tarea": 4, "titulo": "Por vencer", "estado": "PENDIENTE",
        "prioridad": "MEDIA", "fecha_vencimiento": "2026-09-20",
        "cliente": "Cliente Y", "responsable": "Zutano", "dias_restantes": 3,
    }]
    connection = fake_connection_factory(_handler(tareas))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    data = client.get("/api/tareas/por-vencer").get_json()

    assert data[0]["dias_restantes"] == 3
