# -*- coding: utf-8 -*-
"""RF50 — Resumiendo por Estado de Tareas.

GET /api/tareas/resumen: conteo por cada uno de los cinco estados, incluidos
los que estén en cero (mismo patrón que resumen_clientes_dashboard).
"""
from tests.conftest import normalize_sql

import backend.routes.tareas_routes as tareas_routes


def _handler(conteos):
    def handler(sql, params, cursor):
        if "GROUP BY estado" in normalize_sql(sql):
            return [{"estado": estado, "total": total} for estado, total in conteos.items()]
        return []
    return handler


def test_incluye_los_cinco_estados_aunque_alguno_este_en_cero(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    connection = fake_connection_factory(_handler({"PENDIENTE": 3, "EN_PROCESO": 1}))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    data = client.get("/api/tareas/resumen").get_json()

    assert data == {
        "PENDIENTE": 3,
        "EN_PROCESO": 1,
        "EN_REVISION": 0,
        "COMPLETADA": 0,
        "CANCELADA": 0,
    }


def test_administrador_no_filtra_por_responsable(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    connection = fake_connection_factory(_handler({}))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    client.get("/api/tareas/resumen")

    sql, params = connection.executed[-1]
    assert "WHERE" not in normalize_sql(sql)
    assert params == ()


def test_usuario_no_administrador_solo_cuenta_lo_propio(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=6, rol_id=2)

    connection = fake_connection_factory(_handler({}))
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    client.get("/api/tareas/resumen")

    sql, params = connection.executed[-1]
    assert "WHERE id_responsable = %s" in normalize_sql(sql)
    assert params == (6,)
