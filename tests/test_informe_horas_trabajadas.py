import io
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

import backend.routes.reportes_routes as reportes_routes
from tests.conftest import normalize_sql


URL = "/api/reportes/horas-trabajadas"
ROOT = Path(__file__).resolve().parents[1]
PARAMETROS = {
    "agrupar_por": "cliente",
    "granularidad": None,
    "fecha_inicio": None,
    "fecha_fin": None,
    "id_cliente": None,
    "id_tarea": None,
    "id_usuario": None,
}


def _filas_para(sql):
    if "GROUP BY DATE_FORMAT(rt.fecha, '%Y-%m')" in sql:
        return [{
            "clave": "2026-10",
            "etiqueta": "10-2026",
            "detalle": None,
            "minutos": Decimal("90.00"),
            "monto": Decimal("45000.00"),
            "registros": 2,
        }]
    if "GROUP BY rt.fecha" in sql:
        return [{
            "clave": date(2026, 10, 5),
            "etiqueta": "05-10-2026",
            "detalle": None,
            "minutos": Decimal("90.00"),
            "monto": Decimal("45000.00"),
            "registros": 2,
        }]
    if "GROUP BY rt.id_tarea" in sql:
        return [{
            "clave": 3,
            "etiqueta": "Tarea de prueba",
            "detalle": "Cliente de prueba",
            "minutos": Decimal("90.00"),
            "monto": Decimal("45000.00"),
            "registros": 2,
        }]
    if "GROUP BY rt.id_usuario" in sql:
        return [{
            "clave": 4,
            "etiqueta": "Usuario de prueba",
            "detalle": None,
            "minutos": Decimal("90.00"),
            "monto": Decimal("45000.00"),
            "registros": 2,
        }]
    return [
        {
            "clave": 7,
            "etiqueta": "Cliente de prueba",
            "detalle": None,
            "minutos": Decimal("1.00"),
            "monto": Decimal("0.50"),
            "registros": 1,
        },
        {
            "clave": 8,
            "etiqueta": "Cliente dos",
            "detalle": None,
            "minutos": Decimal("1.00"),
            "monto": Decimal("0.50"),
            "registros": 1,
        },
    ]


def _handler(
    capturado,
    *,
    filas=None,
    cliente_existe=True,
    tarea_existe=True,
    usuario_existe=True,
    valores_fila=None,
    reporte_guardado=None,
):
    def manejar(sql, params, cursor):
        sql_normalizado = normalize_sql(sql)
        capturado.setdefault("consultas", []).append((sql_normalizado, params))

        if "FROM reporte WHERE id_reporte = LAST_INSERT_ID()" in sql_normalizado:
            return [{
                "id_reporte": 25,
                "fecha_generacion": "06-11-2026 10:30",
            }]
        if "FROM reporte WHERE id_reporte = %s" in sql_normalizado:
            return [reporte_guardado] if reporte_guardado else []
        if "FROM cliente WHERE id_cliente = %s" in sql_normalizado:
            if not cliente_existe:
                return []
            return [{"id_cliente": params[0], "razon_social": "Cliente de prueba", "rut": "11.111.111-1"}]
        if "FROM tarea t" in sql_normalizado and "WHERE t.id_tarea = %s" in sql_normalizado:
            if not tarea_existe:
                return []
            return [{"id_tarea": params[0], "titulo": "Tarea de prueba", "id_cliente": 7, "cliente": "Cliente de prueba"}]
        if "FROM usuario WHERE id_usuario = %s" in sql_normalizado:
            if not usuario_existe:
                return []
            return [{"id_usuario": params[0], "nombres": "Usuario de prueba"}]
        if "FROM registro_tiempo rt" in sql_normalizado and "GROUP BY" in sql_normalizado:
            if "hora_fin IS NOT NULL" not in sql_normalizado:
                raise AssertionError("El informe debe excluir registros abiertos.")
            capturado["sql_consulta"] = sql_normalizado
            capturado["parametros_sql"] = params
            return valores_fila if valores_fila is not None else (filas if filas is not None else _filas_para(sql_normalizado))
        if "MONEDA_DEFAULT" in sql_normalizado:
            return [{"valor_parametro": "CLP"}]
        if "INSERT INTO reporte" in sql_normalizado:
            capturado["insercion"] = params
            return []
        return []

    return manejar


@pytest.fixture
def generar(client, iniciar_sesion, fake_connection_factory, monkeypatch):
    iniciar_sesion(usuario_id=1, rol_id=1)

    def _generar(consulta, **opciones):
        capturado = {}
        conexion = fake_connection_factory(_handler(capturado, **opciones))
        monkeypatch.setattr(reportes_routes, "get_connection", lambda: conexion)
        return client.get(URL, query_string=consulta), capturado, conexion

    return _generar


def _reporte_guardado(parametros):
    return {
        "id_reporte": 25,
        "tipo_reporte": "HORAS_TRABAJADAS",
        "parametros": json.dumps(parametros),
        "fecha_generacion": datetime(2026, 11, 6, 10, 30),
    }


@pytest.mark.parametrize("rol_id", [2, 3])
def test_solo_administrador_puede_generar_el_informe(client, iniciar_sesion, rol_id):
    iniciar_sesion(usuario_id=2, rol_id=rol_id)
    assert client.get(URL, query_string={"agrupar_por": "cliente"}).status_code == 403


def test_el_informe_requiere_sesion(client):
    assert client.get(URL, query_string={"agrupar_por": "cliente"}).status_code == 401


@pytest.mark.parametrize(
    "query,error",
    [
        ({}, "Debe indicar agrupar_por"),
        ({"agrupar_por": "campo"}, "Debe indicar agrupar_por"),
        ({"agrupar_por": "periodo", "granularidad": "semana"}, "granularidad debe ser dia o mes"),
        ({"agrupar_por": "cliente", "fecha_inicio": "2026-10-01"}, "Debe indicar fecha_inicio y fecha_fin"),
        ({"agrupar_por": "cliente", "fecha_fin": "2026-10-31"}, "Debe indicar fecha_inicio y fecha_fin"),
        ({"agrupar_por": "cliente", "fecha_inicio": "01-10-2026", "fecha_fin": "2026-10-31"}, "formato AAAA-MM-DD"),
        ({"agrupar_por": "cliente", "fecha_inicio": "2026-11-01", "fecha_fin": "2026-10-31"}, "no puede ser posterior"),
        ({"agrupar_por": "cliente", "periodo_etiqueta": "mes"}, "periodo_etiqueta requiere"),
        ({"agrupar_por": "cliente", "periodo_etiqueta": "invalido"}, "periodo_etiqueta no es válido"),
        ({"agrupar_por": "cliente", "id_cliente": "abc"}, "id_cliente debe ser un ID entero positivo"),
        ({"agrupar_por": "cliente", "id_tarea": "0"}, "id_tarea debe ser un ID entero positivo"),
        ({"agrupar_por": "cliente", "id_usuario": "-1"}, "id_usuario debe ser un ID entero positivo"),
        ({"agrupar_por": "cliente", "id_cliente": "1 OR 1=1"}, "id_cliente debe ser un ID entero positivo"),
        ({"agrupar_por": "cliente", "id_tarea": "1; DROP TABLE tarea"}, "id_tarea debe ser un ID entero positivo"),
        ({"agrupar_por": "cliente", "id_usuario": "1' OR '1'='1"}, "id_usuario debe ser un ID entero positivo"),
    ],
)
def test_parametros_invalidos_se_rechazan_antes_de_consultar(generar, query, error):
    respuesta, capturado, _ = generar(query)

    assert respuesta.status_code == 400
    assert error in respuesta.get_json()["error"]
    assert "sql_consulta" not in capturado


@pytest.mark.parametrize(
    "nombre,query,fila_esperada",
    [
        ("cliente", {"agrupar_por": "cliente"}, {"clave": "7", "etiqueta": "Cliente de prueba", "detalle": None, "horas": 0.02, "registros": 1, "monto": 0.5}),
        ("tarea", {"agrupar_por": "tarea"}, {"clave": "3", "etiqueta": "Tarea de prueba", "detalle": "Cliente de prueba", "horas": 1.5, "registros": 2, "monto": 45000.0}),
        ("usuario", {"agrupar_por": "usuario"}, {"clave": "4", "etiqueta": "Usuario de prueba", "detalle": None, "horas": 1.5, "registros": 2, "monto": 45000.0}),
        ("dia", {"agrupar_por": "periodo", "granularidad": "dia"}, {"clave": "2026-10-05", "etiqueta": "05-10-2026", "detalle": None, "horas": 1.5, "registros": 2, "monto": 45000.0}),
        ("mes", {"agrupar_por": "periodo", "granularidad": "mes"}, {"clave": "2026-10", "etiqueta": "10-2026", "detalle": None, "horas": 1.5, "registros": 2, "monto": 45000.0}),
    ],
)
def test_agrupaciones_devuelven_filas_y_totales(nombre, query, fila_esperada, generar):
    respuesta, capturado, _ = generar(query)

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["filas"][0] == fila_esperada
    assert datos["agrupar_por"] == ("periodo" if nombre in {"dia", "mes"} else nombre)
    assert datos["granularidad"] == (nombre if nombre in {"dia", "mes"} else None)
    assert datos["periodo"]["todos_los_registros"] is True
    assert datos["totales"] == {"horas": 0.03 if nombre == "cliente" else 1.5, "monto": 1.0 if nombre == "cliente" else 45000.0, "registros": 2}
    assert datos["id_reporte"] == 25
    assert capturado["insercion"][1] == "HORAS_TRABAJADAS"
    assert json.loads(capturado["insercion"][2])["agrupar_por"] == datos["agrupar_por"]


def test_consulta_usa_parametros_y_filtros_de_fecha_inclusivos(generar):
    query = {
        "agrupar_por": "cliente",
        "fecha_inicio": "2026-10-01",
        "fecha_fin": "2026-10-31",
        "periodo_etiqueta": "mes",
        "id_cliente": "7",
        "id_tarea": "3",
        "id_usuario": "4",
    }
    respuesta, capturado, _ = generar(query)

    assert respuesta.status_code == 200
    assert "rt.fecha BETWEEN %s AND %s" in capturado["sql_consulta"]
    assert all(f"{columna} = %s" in capturado["sql_consulta"] for columna in (
        "rt.id_cliente", "rt.id_tarea", "rt.id_usuario"
    ))
    assert capturado["parametros_sql"] == ("2026-10-01", "2026-10-31", 7, 3, 4)
    assert "2026-10-01" not in capturado["sql_consulta"]
    assert respuesta.get_json()["periodo"]["etiqueta"] == "Último mes"
    assert respuesta.get_json()["periodo"]["todos_los_registros"] is False


@pytest.mark.parametrize(
    "parametro,opcion,error",
    [
        ("id_cliente", {"cliente_existe": False}, "Cliente inexistente."),
        ("id_tarea", {"tarea_existe": False}, "Tarea inexistente."),
        ("id_usuario", {"usuario_existe": False}, "Usuario inexistente."),
    ],
)
def test_filtro_con_entidad_inexistente_responde_404(generar, parametro, opcion, error):
    respuesta, capturado, _ = generar(
        {"agrupar_por": "cliente", parametro: "77"},
        **opcion,
    )

    assert respuesta.status_code == 404
    assert respuesta.get_json()["error"] == error
    assert "sql_consulta" not in capturado


def test_sin_resultados_no_registra_generacion(generar):
    respuesta, capturado, conexion = generar(
        {"agrupar_por": "cliente"},
        filas=[],
    )

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["mensaje"] == "No se registran horas trabajadas para los criterios seleccionados"
    assert datos["filas"] == []
    assert "id_reporte" not in datos
    assert "insercion" not in capturado
    assert conexion.commits == 0


@pytest.mark.parametrize(
    "agrupar_por,granularidad,encabezados",
    [
        ("cliente", None, ["Cliente", "Horas", "Registros", "Monto (CLP)"]),
        ("tarea", None, ["Tarea", "Cliente", "Horas", "Registros", "Monto (CLP)"]),
        ("usuario", None, ["Usuario", "Horas", "Registros", "Monto (CLP)"]),
        ("periodo", "dia", ["Día", "Horas", "Registros", "Monto (CLP)"]),
        ("periodo", "mes", ["Mes", "Horas", "Registros", "Monto (CLP)"]),
    ],
)
def test_exportaciones_excel_y_pdf_reutilizan_la_consulta(
    client,
    iniciar_sesion,
    monkeypatch,
    fake_connection_factory,
    agrupar_por,
    granularidad,
    encabezados,
):
    iniciar_sesion(usuario_id=1, rol_id=1)
    parametros = {**PARAMETROS, "agrupar_por": agrupar_por, "granularidad": granularidad}
    capturado = {}
    conexion = fake_connection_factory(_handler(
        capturado,
        reporte_guardado=_reporte_guardado(parametros),
    ))
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: conexion)

    respuesta_excel = client.get("/api/reportes/25/excel")
    assert respuesta_excel.status_code == 200
    libro = load_workbook(io.BytesIO(respuesta_excel.data), data_only=False)
    hoja = libro["Reporte"]
    assert [celda.value for celda in hoja[1]] == encabezados
    assert hoja.max_row == (3 if agrupar_por == "cliente" else 2)
    assert libro["Parámetros"]["A1"].value == "Reporte"
    assert libro["Parámetros"]["A2"].value == "Período"
    assert "Total de horas" in [libro["Parámetros"].cell(row, 1).value for row in range(1, libro["Parámetros"].max_row + 1)]
    assert "Monto total" in [libro["Parámetros"].cell(row, 1).value for row in range(1, libro["Parámetros"].max_row + 1)]

    conexion_pdf = fake_connection_factory(_handler(
        {},
        reporte_guardado=_reporte_guardado(parametros),
    ))
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: conexion_pdf)
    respuesta_pdf = client.get("/api/reportes/25/pdf")
    assert respuesta_pdf.status_code == 200
    texto_pdf = "\n".join(pagina.extract_text() or "" for pagina in PdfReader(io.BytesIO(respuesta_pdf.data)).pages)
    assert "Horas trabajadas" in texto_pdf
    assert ("0.5" if agrupar_por == "cliente" else "45.000") in texto_pdf


def test_texto_de_usuario_con_prefijo_formula_se_exporta_como_texto(
    client, iniciar_sesion, monkeypatch, fake_connection_factory
):
    iniciar_sesion(usuario_id=1, rol_id=1)
    parametros = {**PARAMETROS, "agrupar_por": "cliente"}
    filas = [{
        "clave": 7,
        "etiqueta": "=HYPERLINK(\"https://example.invalid\")",
        "detalle": None,
        "minutos": Decimal("60"),
        "monto": Decimal("30000"),
        "registros": 1,
    }]
    conexion = fake_connection_factory(_handler(
        {},
        reporte_guardado=_reporte_guardado(parametros),
        valores_fila=filas,
    ))
    monkeypatch.setattr(reportes_routes, "get_connection", lambda: conexion)

    respuesta = client.get("/api/reportes/25/excel")
    assert respuesta.status_code == 200
    hoja = load_workbook(io.BytesIO(respuesta.data), data_only=False)["Reporte"]
    assert hoja["A2"].value == filas[0]["etiqueta"]
    assert hoja["A2"].data_type == "s"


@pytest.mark.parametrize(
    "consulta,orden",
    [
        ({"agrupar_por": "cliente"}, "ORDER BY c.razon_social ASC"),
        ({"agrupar_por": "tarea"}, "ORDER BY c.razon_social ASC, t.titulo ASC"),
        ({"agrupar_por": "usuario"}, "ORDER BY u.nombres ASC"),
        ({"agrupar_por": "periodo", "granularidad": "dia"}, "ORDER BY rt.fecha ASC"),
        (
            {"agrupar_por": "periodo", "granularidad": "mes"},
            "ORDER BY DATE_FORMAT(rt.fecha, '%Y-%m') ASC",
        ),
    ],
)
def test_agrupaciones_ordenan_conforme_a_su_etiqueta(generar, consulta, orden):
    respuesta, capturado, _ = generar(consulta)

    assert respuesta.status_code == 200
    assert orden in capturado["sql_consulta"]


def test_frontend_de_horas_conserva_tipos_y_renderiza_sin_html_inyectado():
    html = (ROOT / "frontend/reportes/reportes.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/reportes/reportes.js").read_text(encoding="utf-8")

    for texto in (
        '<optgroup label="Tareas">',
        '<option value="cliente">',
        '<option value="responsable">',
        '<option value="area">',
        '<optgroup label="Horas">',
        '<option value="horas">',
        '<option value="cobro">',
        'id="selectAgruparHoras"',
        'id="selectGranularidad"',
        'id="selectHorasCliente"',
        'id="selectHorasTarea"',
        'id="selectHorasUsuario"',
        'id="ayudaPeriodoHoras"',
        'id="resultadoHoras"',
        'id="resumenHoras"',
        'id="encabezadoTablaHoras"',
        'id="cuerpoTablaHoras"',
    ):
        assert texto in html

    assert 'new URLSearchParams(window.location.search).get("tipo") === "horas"' in js
    assert 'params.set("agrupar_por", selectAgruparHoras.value)' in js
    assert "async function cargarCatalogosHoras()" in js
    assert "function renderizarResultadoHoras(data)" in js
    renderizador = js.split("function renderizarResultadoHoras(data)", 1)[1].split(
        "// RF75 — monto a cobrar", 1
    )[0]
    assert "innerHTML" not in renderizador

    control_horas = (ROOT / "frontend/control_horas/control_horas.js").read_text(encoding="utf-8")
    assert "innerHTML" not in control_horas
