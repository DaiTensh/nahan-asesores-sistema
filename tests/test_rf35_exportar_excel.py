# -*- coding: utf-8 -*-
"""RF35 — Exportando Reportes en Formato Excel.

GET /api/reportes/<id_reporte>/excel vuelve a consultar con los parámetros
guardados en `reporte` (misma capa que usaría el PDF de RF34, ver
_datos_para_exportar en reportes_routes.py) y arma un .xlsx: una fila por
tarea (o por usuario en productividad) y los encabezados del reporte.
"""
import io
import json

from openpyxl import load_workbook

from tests.conftest import normalize_sql

import backend.routes.reportes_routes as reportes_routes


def _handler_tareas_por_cliente():
    reporte_guardado = {
        "id_reporte": 1,
        "tipo_reporte": "TAREAS_POR_CLIENTE",
        "parametros": json.dumps({
            "id_cliente": 10, "fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31",
        }),
    }
    tareas = [
        {
            "id_tarea": 1, "titulo": "Tarea A", "estado": "PENDIENTE", "prioridad": "ALTA",
            "fecha_creacion": "01-01-2026 10:00", "fecha_vencimiento": "10-01-2026",
            "id_cliente": 10, "cliente": "Cliente Diez",
            "id_responsable": 2, "responsable": "Fulano",
        },
    ]

    def handler(sql, params, cursor):
        sql_normalizado = normalize_sql(sql)
        if "FROM reporte WHERE id_reporte" in sql_normalizado:
            return [reporte_guardado]
        if "FROM tarea t" in sql_normalizado and "INNER JOIN cliente c" in sql_normalizado:
            return [f.copy() for f in tareas]
        if "SELECT razon_social FROM cliente" in sql_normalizado:
            return [{"razon_social": "Cliente Diez"}]
        return []

    return handler


def _handler_productividad():
    reporte_guardado = {
        "id_reporte": 2,
        "tipo_reporte": "PRODUCTIVIDAD_POR_USUARIO",
        "parametros": json.dumps({
            "fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31", "id_area": None,
        }),
    }
    usuarios = [{"id_usuario": 2, "nombres": "Fulano", "id_area": 1}]

    def handler(sql, params, cursor):
        sql_normalizado = normalize_sql(sql)
        if "FROM reporte WHERE id_reporte" in sql_normalizado:
            return [reporte_guardado]
        if "SELECT id_usuario, nombres, id_area FROM usuario" in sql_normalizado:
            return [u.copy() for u in usuarios]
        return []

    return handler


def _leer_xlsx(response):
    libro = load_workbook(io.BytesIO(response.data))
    return list(libro.active.iter_rows(values_only=True))


def test_solo_administrador_puede_exportar(client, iniciar_sesion):
    iniciar_sesion(usuario_id=1, rol_id=2)

    respuesta = client.get("/api/reportes/1/excel")

    assert respuesta.status_code == 403


def test_reporte_inexistente_responde_404(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    connection = fake_connection_factory(lambda sql, params, cursor: [])
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: connection)

    respuesta = client.get("/api/reportes/999/excel")

    assert respuesta.status_code == 404


def test_exporta_tareas_por_cliente_una_fila_por_tarea(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    connection = fake_connection_factory(_handler_tareas_por_cliente())
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: connection)

    respuesta = client.get("/api/reportes/1/excel")

    assert respuesta.status_code == 200
    assert respuesta.headers["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "Cliente_Diez" in respuesta.headers["Content-Disposition"]
    assert "2026-01-01_a_2026-01-31" in respuesta.headers["Content-Disposition"]

    filas = _leer_xlsx(respuesta)
    assert filas[0] == ("Título", "Cliente", "Responsable", "Estado", "Prioridad",
                         "Fecha de creación", "Fecha de vencimiento")
    assert filas[1] == ("Tarea A", "Cliente Diez", "Fulano", "PENDIENTE", "ALTA",
                         "01-01-2026 10:00", "10-01-2026")
    assert len(filas) == 2


def test_exporta_productividad_una_fila_por_usuario(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    connection = fake_connection_factory(_handler_productividad())
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: connection)

    respuesta = client.get("/api/reportes/2/excel")

    assert respuesta.status_code == 200
    filas = _leer_xlsx(respuesta)
    assert filas[0] == ("Usuario", "Tareas completadas",
                         "Tiempo promedio de resolución (horas)", "Carga vigente")
    # openpyxl relee una celda escrita como "" como None: no es un valor real.
    assert filas[1] == ("Fulano", 0, None, 0)
