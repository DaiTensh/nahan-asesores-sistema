# -*- coding: utf-8 -*-
"""RF75 — Calculando el monto a cobrar a un cliente por las horas registradas.

El texto oficial exige: calcular el monto total de un cliente a partir de las
horas de sus tareas y la tarifa aplicable, para un período o para la totalidad de
los registros, mostrarlo desglosando horas, tarifa y monto, y poder exportarlo como
parte de un reporte. Se resuelve como un reporte más de reportes_routes.py
(GET /api/reportes/cobro-por-cliente) que se exporta con los mismos PDF y Excel.
"""
import io
import json
from datetime import date, datetime
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

import backend.routes.reportes_routes as reportes_routes
from tests.conftest import normalize_sql

URL = "/api/reportes/cobro-por-cliente"

REGISTROS = [
    {"fecha": date(2026, 10, 5), "tarea": "Tarea A", "usuario": "Fulano",
     "duracion_minutos": Decimal("90.00"), "tarifa_hora": Decimal("30000.00"), "monto": Decimal("45000.00")},
    {"fecha": date(2026, 10, 6), "tarea": "Tarea B", "usuario": "Zutano",
     "duracion_minutos": Decimal("30.00"), "tarifa_hora": Decimal("30000.00"), "monto": Decimal("15000.00")},
    {"fecha": date(2026, 10, 20), "tarea": "Tarea A", "usuario": "Fulano",
     "duracion_minutos": Decimal("45.00"), "tarifa_hora": Decimal("36000.00"), "monto": Decimal("27000.00")},
]


def _handler(registros=REGISTROS, capturado=None, cliente_existe=True, tipo_guardado=None, parametros_guardados=None):
    capturado = {} if capturado is None else capturado

    def handler(sql, params, cursor):
        sql_n = normalize_sql(sql)
        if "LAST_INSERT_ID()" in sql_n:
            return [{"id_reporte": 7, "fecha_generacion": "03-11-2026 09:30"}]
        if "FROM reporte WHERE id_reporte" in sql_n:
            return [{"id_reporte": 7, "tipo_reporte": tipo_guardado or "COBRO_POR_CLIENTE",
                     "parametros": json.dumps(parametros_guardados),
                     "fecha_generacion": datetime(2026, 11, 3, 9, 30)}]
        if "FROM cliente WHERE id_cliente" in sql_n:
            return [{"id_cliente": 10, "rut": "11.111.111-1", "razon_social": "Cliente Diez"}] if cliente_existe else []
        if "FROM registro_tiempo rt" in sql_n:
            capturado["sql_registros"] = sql_n
            capturado["params_registros"] = params
            return [r.copy() for r in registros]
        if "MONEDA_DEFAULT" in sql_n:
            return [{"valor_parametro": "CLP"}]
        if "INSERT INTO reporte" in sql_n:
            capturado["insert"] = (params[1], json.loads(params[2]))
        return []
    return handler


@pytest.fixture
def generar(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    def _generar(consulta, **opciones):
        capturado = opciones.pop("capturado", {})
        conexion = fake_connection_factory(_handler(capturado=capturado, **opciones))
        monkeypatch.setattr(reportes_routes, "get_connection", lambda: conexion)
        return client.get(URL, query_string=consulta), capturado
    return _generar


# ---------------------------------------------------------------------------
# Acceso y validación
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rol_id", [2, 3])
def test_solo_el_administrador_ve_el_cobro(client, iniciar_sesion, rol_id):
    iniciar_sesion(usuario_id=2, rol_id=rol_id)
    assert client.get(URL, query_string={"id_cliente": 10}).status_code == 403


def test_sin_sesion_no_se_accede(client):
    assert client.get(URL, query_string={"id_cliente": 10}).status_code == 401


@pytest.mark.parametrize("consulta,mensaje", [
    ({}, "Debe indicar id_cliente."),
    ({"id_cliente": "abc"}, "id_cliente debe ser un ID entero positivo"),
    ({"id_cliente": "0"}, "id_cliente debe ser un ID entero positivo"),
    ({"id_cliente": "10", "fecha_inicio": "2026-10-01"}, "Debe indicar fecha_inicio y fecha_fin"),
    ({"id_cliente": "10", "fecha_fin": "2026-10-31"}, "Debe indicar fecha_inicio y fecha_fin"),
    ({"id_cliente": "10", "fecha_inicio": "01-10-2026", "fecha_fin": "31-10-2026"}, "formato AAAA-MM-DD"),
    ({"id_cliente": "10", "fecha_inicio": "2026-11-01", "fecha_fin": "2026-10-31"}, "no puede ser posterior"),
    ({"id_cliente": "10", "periodo_etiqueta": "mes"}, "periodo_etiqueta requiere"),
    ({"id_cliente": "10", "fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-31", "periodo_etiqueta": "x"}, "periodo_etiqueta no es válido"),
])
def test_los_parametros_invalidos_se_rechazan_sin_consultar(generar, consulta, mensaje):
    respuesta, capturado = generar(consulta)
    assert respuesta.status_code == 400 and mensaje in respuesta.get_json()["error"]
    assert "sql_registros" not in capturado


def test_un_cliente_inexistente_responde_404(generar):
    respuesta, _ = generar({"id_cliente": 99}, cliente_existe=False)
    assert respuesta.status_code == 404


# ---------------------------------------------------------------------------
# Cálculo y desglose
# ---------------------------------------------------------------------------

def test_calcula_horas_tarifa_y_monto_de_un_periodo(generar):
    respuesta, capturado = generar({"id_cliente": 10, "fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-31"})

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["cliente"]["razon_social"] == "Cliente Diez" and datos["moneda"] == "CLP"
    assert datos["periodo"] == {"fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-31", "todos_los_registros": False}
    assert datos["totales"] == {"horas": 2.75, "monto": 87000.0, "registros": 3}
    assert datos["desglose_por_tarifa"] == [
        {"tarifa_hora": 30000.0, "horas": 2.0, "monto": 60000.0},
        {"tarifa_hora": 36000.0, "horas": 0.75, "monto": 27000.0},
    ]
    assert datos["registros"][0] == {"fecha": "2026-10-05", "tarea": "Tarea A", "usuario": "Fulano",
                                      "horas": 1.5, "tarifa_hora": 30000.0, "monto": 45000.0}
    assert datos["id_reporte"] == 7 and datos["fecha_generacion"] == "03-11-2026 09:30"
    assert "rt.fecha BETWEEN %s AND %s" in capturado["sql_registros"]
    assert capturado["params_registros"] == (10, "2026-10-01", "2026-10-31")
    assert capturado["insert"] == ("COBRO_POR_CLIENTE", {
        "id_cliente": 10, "fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-31"})


def test_sin_fechas_calcula_la_totalidad_de_los_registros(generar):
    respuesta, capturado = generar({"id_cliente": 10})

    datos = respuesta.get_json()
    assert respuesta.status_code == 200
    assert datos["periodo"] == {"fecha_inicio": None, "fecha_fin": None, "todos_los_registros": True}
    assert "BETWEEN" not in capturado["sql_registros"] and capturado["params_registros"] == (10,)
    assert capturado["insert"][1] == {"id_cliente": 10, "fecha_inicio": None, "fecha_fin": None}


def test_solo_cuentan_los_registros_cerrados(generar):
    _, capturado = generar({"id_cliente": 10})
    assert "rt.hora_fin IS NOT NULL" in capturado["sql_registros"]


def test_las_horas_totales_se_suman_antes_de_redondear():
    """Tres registros de 20 minutos son 1 hora, no 3 × 0,33."""
    class Cursor:
        def execute(self, sql, params=None): pass

        def fetchall(self):
            return [{"fecha": date(2026, 10, d), "tarea": "T", "usuario": "U", "duracion_minutos": Decimal("20.00"),
                     "tarifa_hora": Decimal("30000.00"), "monto": Decimal("10000.00")} for d in (1, 2, 3)]

    registros, desglose, totales = reportes_routes._consultar_cobro_cliente(Cursor(), 1)
    assert totales["horas"] == Decimal("1.00") and totales["monto"] == Decimal("30000.00")
    assert [r["horas"] for r in registros] == [Decimal("0.33")] * 3
    assert desglose[0]["horas"] == Decimal("1.00")


def test_un_cliente_sin_horas_responde_con_un_mensaje_y_sin_reporte(generar):
    respuesta, capturado = generar({"id_cliente": 10, "fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-31"}, registros=[])

    datos = respuesta.get_json()
    assert respuesta.status_code == 200 and "No se registran horas" in datos["mensaje"]
    assert "id_reporte" not in datos and "insert" not in capturado
    assert datos["totales"] == {"horas": 0.0, "monto": 0.0, "registros": 0}


def test_el_atajo_de_periodo_se_guarda(generar):
    respuesta, capturado = generar({"id_cliente": 10, "fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-31",
                                    "periodo_etiqueta": "mes"})
    assert respuesta.get_json()["periodo"]["etiqueta"] == "Último mes"
    assert capturado["insert"][1]["periodo_etiqueta"] == "mes"


def test_el_formato_chileno_usa_punto_de_miles_y_coma_decimal():
    f = reportes_routes._formato_cl
    assert (f(Decimal("1234567.5"), 2), f(Decimal("36000")), f(Decimal("0.5"), 2), f(5, 2)) == ("1.234.567,50", "36.000", "0,50", "5,00")


# ---------------------------------------------------------------------------
# Exportación como parte de un reporte (PDF y Excel)
# ---------------------------------------------------------------------------

@pytest.fixture
def exportar(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    def _exportar(formato, parametros):
        conexion = fake_connection_factory(_handler(parametros_guardados=parametros))
        monkeypatch.setattr(reportes_routes, "get_connection", lambda: conexion)
        return client.get(f"/api/reportes/7/{formato}")
    return _exportar


PERIODO = {"id_cliente": 10, "fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-31"}
TODO = {"id_cliente": 10, "fecha_inicio": None, "fecha_fin": None}


def test_el_excel_trae_una_fila_por_registro_y_los_totales_en_parametros(exportar):
    respuesta = exportar("excel", PERIODO)

    assert respuesta.status_code == 200
    assert "reporte_cobro_por_cliente_Cliente_Diez_2026-10-01_a_2026-10-31.xlsx" in respuesta.headers["Content-Disposition"]
    libro = load_workbook(io.BytesIO(respuesta.data))
    filas = list(libro["Reporte"].values)
    assert filas[0] == ("Fecha", "Tarea", "Usuario", "Horas", "Tarifa por hora (CLP)", "Monto (CLP)")
    assert filas[1] == ("2026-10-05", "Tarea A", "Fulano", 1.5, 30000.0, 45000.0)
    assert len(filas) == 4, "encabezado y una fila por registro; los totales van en «Parámetros»"
    assert sum(f[5] for f in filas[1:]) == 87000.0 and libro["Reporte"]["F2"].data_type == "n"
    parametros = dict(libro["Parámetros"].values)
    assert parametros["Reporte"] == "Cobro por cliente (horas y monto)"
    assert parametros["Período"] == "2026-10-01 a 2026-10-31"
    assert parametros["Cliente"] == "Cliente Diez (11.111.111-1)"
    assert parametros["Total de horas"] == "2,75 h" and parametros["Monto total a cobrar"] == "87.000 CLP"
    assert parametros["Tarifa de 30.000 CLP por hora"] == "2,00 h = 60.000 CLP"
    assert parametros["Tarifa de 36.000 CLP por hora"] == "0,75 h = 27.000 CLP"


def test_el_excel_de_todos_los_registros_lo_dice(exportar):
    respuesta = exportar("excel", TODO)

    assert "todos_los_registros.xlsx" in respuesta.headers["Content-Disposition"]
    assert dict(load_workbook(io.BytesIO(respuesta.data))["Parámetros"].values)["Período"] == "Todos los registros"


def test_el_pdf_muestra_el_desglose_y_el_monto_total(exportar):
    respuesta = exportar("pdf", PERIODO)

    assert respuesta.status_code == 200 and respuesta.mimetype == "application/pdf"
    texto = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(respuesta.data)).pages)
    for esperado in ("Cobro por cliente", "Cliente Diez", "Monto total a cobrar: 87.000 CLP", "Total de horas: 2,75 h",
                     "Tarifa de 30.000 CLP por hora", "Tarea A", "Fulano"):
        assert esperado in texto, esperado


def test_un_texto_de_usuario_no_se_ejecuta_como_formula_en_el_excel(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)
    registros = [dict(REGISTROS[0], tarea='=HYPERLINK("https://example.invalid")')]
    conexion = fake_connection_factory(_handler(registros=registros, parametros_guardados=PERIODO))
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: conexion)

    libro = load_workbook(io.BytesIO(client.get("/api/reportes/7/excel").data))
    assert libro["Reporte"]["B2"].data_type == "s"


# ---------------------------------------------------------------------------
# Pantalla de reportes
# ---------------------------------------------------------------------------

def _leer_frontend(*partes):
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "frontend", *partes), encoding="utf-8") as archivo:
        return archivo.read()


def test_la_pantalla_de_reportes_ofrece_el_cobro_con_periodo_opcional():
    html = _leer_frontend("reportes", "reportes.html")
    js = _leer_frontend("reportes", "reportes.js")
    assert '<option value="cobro">Cobro por cliente (horas y monto)</option>' in html
    assert 'id="ayudaPeriodoCobro"' in html and "puede dejar las fechas vacías" in html
    assert '"cobro-por-cliente"' in js
    assert "inputFechaInicio.required = !esCobro" in js and "Boolean(fechaInicio) !== Boolean(fechaFin)" in js


def test_el_desglose_muestra_horas_tarifa_y_monto_en_tablas_responsivas():
    import re
    html = _leer_frontend("reportes", "reportes.html")
    bloque = html[html.index('id="resultadoCobro"'):html.index('id="resultadoAreas"')]
    for encabezado in ("Tarifa por hora", "Horas trabajadas", "Monto", "Fecha", "Tarea", "Usuario", "Horas"):
        assert f">{encabezado}</th>" in bloque, encabezado
    assert len(re.findall(r'class="table-responsive"', bloque)) == len(re.findall(r"<table", bloque)) == 2


def test_el_resultado_del_cobro_no_inserta_html():
    js = _leer_frontend("reportes", "reportes.js")
    funcion = js[js.index("function renderizarResultadoCobro"):js.index("function renderizarResultadoAreas")]
    assert "innerHTML" not in funcion and "insertAdjacentHTML" not in funcion
    assert 'toLocaleString("es-CL"' in js, "las cifras llevan coma decimal y punto de miles"
