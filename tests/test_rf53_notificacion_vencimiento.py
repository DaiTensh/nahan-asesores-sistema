# -*- coding: utf-8 -*-
"""RF53 — Notificando el Vencimiento de Tareas.

`notificar_vencimientos_proximos()` es el proceso que corre el timer de
systemd (o a mano, para la demostración). No abre una sesión Flask, así que
estas pruebas usan el mismo patrón de `fake_connection_factory` que
test_incremento1_regression.py, sin cliente HTTP.
"""
from tests.conftest import normalize_sql

import backend.tareas_programadas as tareas_programadas


def _handler(tareas_por_vencer, ya_notificadas=frozenset()):
    """`ya_notificadas` es un conjunto de (id_usuario, url_destino) para los
    que la consulta de idempotencia debe devolver "ya existe"."""

    def handler(sql, params, cursor):
        sql_normalizado = normalize_sql(sql)

        if "SELECT id_tarea, id_responsable, titulo, fecha_vencimiento FROM tarea" in sql_normalizado:
            return [t.copy() for t in tareas_por_vencer]

        if "SELECT 1 FROM notificacion" in sql_normalizado:
            id_usuario, _tipo, url_destino = params
            return [{"1": 1}] if (id_usuario, url_destino) in ya_notificadas else []

        return []

    return handler


def test_notifica_al_responsable_de_una_tarea_por_vencer(monkeypatch, fake_connection_factory):
    tareas = [{
        "id_tarea": 10,
        "id_responsable": 2,
        "titulo": "Declarar impuestos",
        "fecha_vencimiento": "2026-09-13",
    }]
    connection = fake_connection_factory(_handler(tareas))
    monkeypatch.setattr(tareas_programadas, "get_connection", lambda: connection)

    creadas = tareas_programadas.notificar_vencimientos_proximos(dias=3)

    assert creadas == 1
    inserts = [
        (sql, params) for sql, params in connection.executed
        if "INSERT INTO notificacion" in normalize_sql(sql)
    ]
    assert len(inserts) == 1
    _, params = inserts[0]
    assert params[0] == 2  # id_usuario
    assert params[1] == "VENCIMIENTO_PROXIMO"
    assert "Declarar impuestos" in params[2]
    assert params[3] == "/frontend/tareas/detalle_tarea.html?id=10"
    assert connection.commits == 1


def test_no_duplica_el_aviso_si_ya_se_notifico_hoy(monkeypatch, fake_connection_factory):
    tareas = [{
        "id_tarea": 10,
        "id_responsable": 2,
        "titulo": "Declarar impuestos",
        "fecha_vencimiento": "2026-09-13",
    }]
    ya_notificadas = {(2, "/frontend/tareas/detalle_tarea.html?id=10")}
    connection = fake_connection_factory(_handler(tareas, ya_notificadas))
    monkeypatch.setattr(tareas_programadas, "get_connection", lambda: connection)

    creadas = tareas_programadas.notificar_vencimientos_proximos(dias=3)

    assert creadas == 0
    inserts = [
        sql for sql, _ in connection.executed
        if "INSERT INTO notificacion" in normalize_sql(sql)
    ]
    assert inserts == []


def test_no_hay_tareas_por_vencer_no_crea_avisos(monkeypatch, fake_connection_factory):
    connection = fake_connection_factory(_handler([]))
    monkeypatch.setattr(tareas_programadas, "get_connection", lambda: connection)

    creadas = tareas_programadas.notificar_vencimientos_proximos(dias=3)

    assert creadas == 0


def test_usa_el_umbral_de_dias_indicado(monkeypatch, fake_connection_factory):
    connection = fake_connection_factory(_handler([]))
    monkeypatch.setattr(tareas_programadas, "get_connection", lambda: connection)

    tareas_programadas.notificar_vencimientos_proximos(dias=7)

    seleccion = [
        params for sql, params in connection.executed
        if "SELECT id_tarea, id_responsable, titulo, fecha_vencimiento FROM tarea" in normalize_sql(sql)
    ]
    assert seleccion[0][0] == 7


def test_dias_por_defecto_viene_de_la_variable_de_entorno(monkeypatch, fake_connection_factory):
    monkeypatch.setenv("DIAS_ANTICIPACION_VENCIMIENTO", "5")
    connection = fake_connection_factory(_handler([]))
    monkeypatch.setattr(tareas_programadas, "get_connection", lambda: connection)

    tareas_programadas.notificar_vencimientos_proximos()

    seleccion = [
        params for sql, params in connection.executed
        if "SELECT id_tarea, id_responsable, titulo, fecha_vencimiento FROM tarea" in normalize_sql(sql)
    ]
    assert seleccion[0][0] == 5


def test_proceso_informa_fallo_si_mysql_no_responde(monkeypatch):
    import pytest
    monkeypatch.setattr(tareas_programadas, 'get_connection', lambda: None)
    with pytest.raises(RuntimeError, match='MySQL'):
        tareas_programadas.main()
