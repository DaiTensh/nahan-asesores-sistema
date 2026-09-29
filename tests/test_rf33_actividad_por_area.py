from tests.conftest import normalize_sql

import backend.routes.reportes_routes as reportes_routes


URL = "/api/reportes/actividad-por-area"
FECHA_INICIO = "2026-09-01"
FECHA_FIN = "2026-09-30"

AREAS = [
    {"id_area": 1, "nombre_area": "CONTABLE"},
    {"id_area": 2, "nombre_area": "JURIDICA"},
]
CLIENTES = [{"id_area": 1, "total": 2}, {"id_area": 2, "total": 3}]
TAREAS = [{"id_area": 1, "total": 4}, {"id_area": 2, "total": 7}]
USUARIOS = [{"id_area": 1, "total": 2}, {"id_area": 2, "total": 3}]


def _handler(sql, params, cursor):
    consulta = normalize_sql(sql)
    if "SELECT id_area, nombre_area FROM area" in consulta:
        return [area.copy() for area in AREAS]
    if "FROM cliente_area" in consulta:
        return [fila.copy() for fila in CLIENTES]
    if "FROM tarea WHERE fecha_creacion" in consulta:
        return [fila.copy() for fila in TAREAS]
    if "FROM usuario WHERE estado = 'ACTIVO'" in consulta:
        return [fila.copy() for fila in USUARIOS]
    return []


def _preparar_reporte(monkeypatch, iniciar_sesion, fake_connection_factory, rol_id=1):
    iniciar_sesion(usuario_id=9, rol_id=rol_id)
    conexion = fake_connection_factory(_handler)
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: conexion)
    monkeypatch.setattr(
        reportes_routes,
        "_registrar_generacion",
        lambda cursor, usuario, tipo, parametros: {
            "id_reporte": 45,
            "fecha_generacion": "30-09-2026 12:00",
        },
    )
    return conexion


def _url_periodo():
    return f"{URL}?fecha_inicio={FECHA_INICIO}&fecha_fin={FECHA_FIN}"


def test_resume_y_compara_clientes_tareas_y_usuarios_por_area(
    client, monkeypatch, iniciar_sesion, fake_connection_factory
):
    _preparar_reporte(monkeypatch, iniciar_sesion, fake_connection_factory)

    respuesta = client.get(_url_periodo())
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert {area["nombre_area"] for area in datos["areas"]} == {"JURIDICA", "CONTABLE"}
    por_area = {area["nombre_area"]: area for area in datos["areas"]}
    assert por_area["JURIDICA"] == {
        "id_area": 2, "nombre_area": "JURIDICA", "clientes": 3, "tareas": 7, "usuarios": 3
    }
    assert por_area["CONTABLE"] == {
        "id_area": 1, "nombre_area": "CONTABLE", "clientes": 2, "tareas": 4, "usuarios": 2
    }
    assert datos["comparacion"]["disponible"] is True
    assert datos["comparacion"]["diferencias"] == {"clientes": 1, "tareas": 3, "usuarios": 1}


def test_filtra_las_tres_metricas_por_rango_de_fechas_con_parametros(
    client, monkeypatch, iniciar_sesion, fake_connection_factory
):
    conexion = _preparar_reporte(monkeypatch, iniciar_sesion, fake_connection_factory)

    respuesta = client.get(_url_periodo())

    assert respuesta.status_code == 200
    consulta_tareas = next(
        (sql, parametros)
        for sql, parametros in conexion.executed
        if "FROM tarea" in normalize_sql(sql) and "GROUP BY id_area" in normalize_sql(sql)
    )
    assert consulta_tareas[1] == (FECHA_INICIO, FECHA_FIN)
    assert "%s" in consulta_tareas[0]
    consulta_clientes = next(
        (sql, parametros)
        for sql, parametros in conexion.executed
        if "FROM cliente_area" in normalize_sql(sql)
    )
    consulta_usuarios = next(
        (sql, parametros)
        for sql, parametros in conexion.executed
        if "FROM usuario" in normalize_sql(sql) and "GROUP BY id_area" in normalize_sql(sql)
    )
    assert consulta_clientes[1] == (FECHA_INICIO, FECHA_FIN)
    assert consulta_usuarios[1] == (FECHA_INICIO, FECHA_FIN)


def test_reutiliza_resumen_para_exportacion_excel(
    monkeypatch, iniciar_sesion, fake_connection_factory
):
    conexion = _preparar_reporte(monkeypatch, iniciar_sesion, fake_connection_factory)
    cursor = conexion.cursor(dictionary=True)

    nombre, encabezados, filas = reportes_routes._datos_para_exportar(
        cursor,
        "ACTIVIDAD_POR_AREA",
        {"fecha_inicio": FECHA_INICIO, "fecha_fin": FECHA_FIN},
    )

    assert nombre == "reporte_actividad_por_area_2026-09-01_a_2026-09-30.xlsx"
    assert encabezados == [
        "Área", "Clientes asignados en el período", "Tareas del período",
        "Usuarios activos creados en el período",
    ]
    assert filas == [["CONTABLE", 2, 4, 2], ["JURIDICA", 3, 7, 3]]


def test_valida_fechas_y_etiqueta_de_periodo(
    client, monkeypatch, iniciar_sesion, fake_connection_factory
):
    _preparar_reporte(monkeypatch, iniciar_sesion, fake_connection_factory)

    assert client.get(URL).status_code == 400
    assert client.get(f"{URL}?fecha_inicio=2026-09-31&fecha_fin={FECHA_FIN}").status_code == 400
    assert client.get(f"{URL}?fecha_inicio={FECHA_FIN}&fecha_fin={FECHA_INICIO}").status_code == 400
    assert client.get(f"{_url_periodo()}&periodo_etiqueta=desconocido").status_code == 400


def test_solo_administrador_puede_generar_reporte(
    client, monkeypatch, iniciar_sesion, fake_connection_factory
):
    conexion = _preparar_reporte(monkeypatch, iniciar_sesion, fake_connection_factory, rol_id=2)

    respuesta = client.get(_url_periodo())

    assert respuesta.status_code == 403
    assert conexion.executed == []
