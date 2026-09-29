from tests.conftest import normalize_sql

import backend.routes.tareas_routes as tareas_routes

URL = "/api/tareas/pendientes/resumen"


def _handler(sql, params, cursor):
    consulta = normalize_sql(sql)

    if "COUNT(*) AS total FROM tarea t WHERE" in consulta and "fecha_creacion" in consulta:
        if params[:2] == ("2026-08-01", "2026-08-31"):
            return [{"total": 5}]
        return [{"total": 8}]

    if "COUNT(*) AS total FROM tarea t WHERE t.estado IN" in consulta:
        return [{"total": 8}]

    if "GROUP BY a.id_area, a.nombre_area" in consulta:
        return [
            {"nombre_area": "JURIDICA", "total": 4},
            {"nombre_area": "CONTABLE", "total": 2},
        ]

    if "GROUP BY c.id_cliente, c.razon_social" in consulta:
        return [
            {"id_cliente": 10, "razon_social": "Cliente A", "total": 3},
            {"id_cliente": 11, "razon_social": "Cliente B", "total": 1},
        ]

    if "GROUP BY u.id_usuario, u.nombres" in consulta:
        return [
            {"id_responsable": 2, "nombres": "Ana", "total": 3},
            {"id_responsable": 3, "nombres": "Beto", "total": 2},
        ]

    if "COUNT(*) AS total FROM tarea t WHERE" in consulta and "fecha_creacion" in consulta:
        if params[:2] == ("2026-08-01", "2026-08-31"):
            return [{"total": 5}]
        return [{"total": 8}]

    return []


def test_total_y_desglose_por_area_cliente_y_responsable(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)
    conexion = fake_connection_factory(_handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: conexion)

    respuesta = client.get(URL)
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["total_pendientes"] == 8
    assert datos["por_area"] == [
        {"area": "JURIDICA", "total": 4},
        {"area": "CONTABLE", "total": 2},
    ]
    assert datos["por_cliente"] == [
        {"id_cliente": 10, "cliente": "Cliente A", "total": 3},
        {"id_cliente": 11, "cliente": "Cliente B", "total": 1},
    ]
    assert datos["por_responsable"] == [
        {"id_responsable": 2, "responsable": "Ana", "total": 3},
        {"id_responsable": 3, "responsable": "Beto", "total": 2},
    ]


def test_excluye_tareas_finalizadas(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)
    conexion = fake_connection_factory(_handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: conexion)

    client.get(URL)

    sql_total = conexion.executed[0][0]
    assert "estado IN ('PENDIENTE', 'EN_PROCESO', 'EN_REVISION')" in normalize_sql(sql_total)
    assert "COMPLETADA" not in normalize_sql(sql_total)
    assert "CANCELADA" not in normalize_sql(sql_total)


def test_usuario_no_administrador_solo_ve_sus_tareas(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=6, rol_id=2)
    conexion = fake_connection_factory(_handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: conexion)

    client.get(URL)

    ultima_sql = normalize_sql(conexion.executed[-1][0])
    assert "t.id_responsable = %s" in ultima_sql
    assert conexion.executed[-1][1][-1] == 6


def test_devuelve_cero_y_arreglos_vacios_cuando_no_hay_pendientes(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    def handler(sql, params, cursor):
        consulta = normalize_sql(sql)
        if "COUNT(*) AS total FROM tarea t WHERE" in consulta:
            return [{"total": 0}]
        if "GROUP BY a.id_area" in consulta:
            return []
        if "GROUP BY c.id_cliente" in consulta:
            return []
        if "GROUP BY u.id_usuario" in consulta:
            return []
        return []

    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: conexion)

    respuesta = client.get(URL)
    assert respuesta.status_code == 200
    assert respuesta.get_json() == {
        "total_pendientes": 0,
        "por_area": [],
        "por_cliente": [],
        "por_responsable": [],
        "comparacion": {"disponible": False, "periodo_actual": None, "periodo_anterior": None, "diferencia": 0},
    }


def test_comparacion_con_periodo_anterior_cuando_hay_historial(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)
    conexion = fake_connection_factory(_handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: conexion)

    respuesta = client.get(URL)
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["comparacion"]["disponible"] is True
    assert datos["comparacion"]["diferencia"] == 3


def test_rechaza_parametros_invalidos(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)
    conexion = fake_connection_factory(_handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: conexion)

    respuesta = client.get(f"{URL}?fecha_inicio=2026-09-30")

    assert respuesta.status_code == 400
    assert "fecha_inicio y fecha_fin" in respuesta.get_json()["error"]
