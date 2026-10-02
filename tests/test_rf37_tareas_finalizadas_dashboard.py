from datetime import date, timedelta

from tests.conftest import normalize_sql

import backend.routes.tareas_routes as tareas_routes

URL = "/api/tareas/finalizadas/resumen"


def _mes_anterior(hoy=None):
    """Primer y último día del mes anterior al de `hoy` (por defecto, hoy).

    El resumen compara el mes en curso con el anterior; se calcula igual que
    el endpoint para que la prueba no dependa del mes en que se ejecute
    (incluido el paso de enero a diciembre del año previo).
    """
    hoy = hoy or date.today()
    fin = hoy.replace(day=1) - timedelta(days=1)
    return fin.replace(day=1).isoformat(), fin.isoformat()


def _handler(sql, params, cursor):
    consulta = normalize_sql(sql)

    if "COUNT(*) AS total FROM tarea t WHERE" in consulta and "estado = 'COMPLETADA'" in consulta:
        if params[:2] == _mes_anterior():
            return [{"total": 5}]
        return [{"total": 7}]

    if "COUNT(*) AS total FROM tarea t WHERE" in consulta and "fecha_creacion" in consulta:
        return [{"total": 10}]

    if "GROUP BY a.id_area, a.nombre_area" in consulta:
        return [
            {"nombre_area": "JURIDICA", "total": 4},
            {"nombre_area": "CONTABLE", "total": 3},
        ]

    if "GROUP BY u.id_usuario, u.nombres" in consulta:
        return [
            {"id_usuario": 2, "nombres": "Ana", "total": 3},
            {"id_usuario": 3, "nombres": "Beto", "total": 4},
        ]

    if "GROUP BY c.id_cliente, c.razon_social" in consulta:
        return [
            {"id_cliente": 10, "razon_social": "Cliente A", "total": 3},
            {"id_cliente": 11, "razon_social": "Cliente B", "total": 4},
        ]

    return []


def test_total_desglose_y_porcentaje_de_cumplimiento(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)
    conexion = fake_connection_factory(_handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: conexion)

    respuesta = client.get(URL)
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["total_finalizadas"] == 7
    assert datos["total_asignadas"] == 10
    assert datos["porcentaje_cumplimiento"] == 70.0
    assert datos["por_area"] == [
        {"area": "JURIDICA", "total": 4},
        {"area": "CONTABLE", "total": 3},
    ]
    assert datos["por_usuario"] == [
        {"id_usuario": 2, "usuario": "Ana", "total": 3},
        {"id_usuario": 3, "usuario": "Beto", "total": 4},
    ]
    assert datos["por_cliente"] == [
        {"id_cliente": 10, "cliente": "Cliente A", "total": 3},
        {"id_cliente": 11, "cliente": "Cliente B", "total": 4},
    ]


def test_solo_cuenta_estado_completada_y_excluye_cancelada(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)
    conexion = fake_connection_factory(_handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: conexion)

    client.get(URL)

    sql_total = normalize_sql(conexion.executed[0][0])
    assert "estado = 'COMPLETADA'" in sql_total
    assert "t.fecha_finalizacion >= %s" in sql_total
    assert "t.fecha_finalizacion < DATE_ADD(%s, INTERVAL 1 DAY)" in sql_total
    assert "CANCELADA" not in sql_total


def test_usuario_no_administrador_solo_ve_las_suyas(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=6, rol_id=2)
    conexion = fake_connection_factory(_handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: conexion)

    client.get(URL)

    sql_total = normalize_sql(conexion.executed[0][0])
    assert "t.id_responsable = %s" in sql_total
    assert conexion.executed[0][1][-1] == 6


def test_cumplimiento_cero_cuando_no_hay_tareas_asignadas(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    def handler(sql, params, cursor):
        consulta = normalize_sql(sql)
        if "COUNT(*) AS total FROM tarea t WHERE" in consulta and "estado = 'COMPLETADA'" in consulta:
            return [{"total": 0}]
        if "COUNT(*) AS total FROM tarea t WHERE" in consulta and "fecha_creacion" in consulta:
            return [{"total": 0}]
        if "GROUP BY a.id_area, a.nombre_area" in consulta:
            return []
        if "GROUP BY u.id_usuario, u.nombres" in consulta:
            return []
        if "GROUP BY c.id_cliente, c.razon_social" in consulta:
            return []
        return []

    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: conexion)

    respuesta = client.get(URL)
    assert respuesta.status_code == 200
    assert respuesta.get_json()["porcentaje_cumplimiento"] == 0.0
    assert respuesta.get_json()["total_finalizadas"] == 0
    assert respuesta.get_json()["total_asignadas"] == 0
    assert respuesta.get_json()["comparacion"]["periodo_actual"] is not None


def test_comparacion_con_periodo_anterior(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)
    conexion = fake_connection_factory(_handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: conexion)

    respuesta = client.get(URL)
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["comparacion"]["disponible"] is True
    assert datos["comparacion"]["diferencia"] == 2


def test_rechaza_fechas_incompletas(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)
    conexion = fake_connection_factory(_handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: conexion)

    respuesta = client.get(f"{URL}?fecha_inicio=2026-09-30")

    assert respuesta.status_code == 400
    assert "fecha_inicio y fecha_fin" in respuesta.get_json()["error"]
