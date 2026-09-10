# -*- coding: utf-8 -*-
"""RF48 — Visualizando Tareas Prioritarias.

GET /api/tareas/prioritarias: siempre acotadas al usuario en sesión, sin
importar el rol (a diferencia de RF42/RF43, no hay vista "de todos").
"""
from tests.conftest import normalize_sql

import backend.routes.tareas_routes as tareas_routes


def _handler(tareas):
    def handler(sql, params, cursor):
        if "FROM tarea t" in normalize_sql(sql) and "prioridad IN" in normalize_sql(sql):
            return [f.copy() for f in tareas]
        return []
    return handler


def test_siempre_filtra_por_el_usuario_en_sesion_incluso_admin(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=3, rol_id=1)

    connection = fake_connection_factory(_handler([]))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    client.get("/api/tareas/prioritarias")

    sql, params = connection.executed[-1]
    assert "t.id_responsable = %s" in normalize_sql(sql)
    assert params[0] == 3


def test_solo_incluye_alta_y_urgente(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=3, rol_id=1)

    connection = fake_connection_factory(_handler([]))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    client.get("/api/tareas/prioritarias")

    sql, _ = connection.executed[-1]
    assert "'ALTA', 'URGENTE'" in normalize_sql(sql)


def test_excluye_completadas_y_canceladas(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=3, rol_id=1)

    connection = fake_connection_factory(_handler([]))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    client.get("/api/tareas/prioritarias")

    sql, _ = connection.executed[-1]
    assert "NOT IN ('COMPLETADA', 'CANCELADA')" in normalize_sql(sql)


def test_devuelve_las_tareas_del_usuario(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=3, rol_id=1)

    tareas = [
        {"id_tarea": 1, "titulo": "Urgente", "estado": "PENDIENTE",
         "prioridad": "URGENTE", "fecha_vencimiento": "2026-09-20", "cliente": "Cliente Z"},
    ]
    connection = fake_connection_factory(_handler(tareas))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    data = client.get("/api/tareas/prioritarias").get_json()

    assert data == tareas
