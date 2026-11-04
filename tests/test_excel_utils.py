"""Escritura de hojas de Excel: fórmulas neutralizadas y tiempo lineal en el número de filas."""
import datetime
import io
from decimal import Decimal

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from backend.routes import clientes_routes
from backend.utils.excel import escribir_filas
from tests.conftest import normalize_sql


def _hoja():
    return Workbook().active


def test_escribe_desde_la_fila_indicada_y_devuelve_la_siguiente():
    hoja = _hoja()
    assert escribir_filas(hoja, [["a", "b"]]) == 2
    assert escribir_filas(hoja, [["c", "d"], ["e", "f"]], fila_inicial=2) == 4
    assert list(hoja.values) == [("a", "b"), ("c", "d"), ("e", "f")]


def test_un_texto_que_parece_formula_queda_como_texto():
    hoja = _hoja()
    formula = '=HYPERLINK("https://example.invalid")'
    escribir_filas(hoja, [[formula, "=1+1", "texto", 5]])
    assert [c.data_type for c in hoja[1]] == ["s", "s", "s", "n"]
    libro = load_workbook(_guardar(hoja.parent))
    assert libro.active["A1"].value == formula and libro.active["A1"].data_type == "s"


def test_conserva_numeros_fechas_decimales_y_vacios():
    hoja = _hoja()
    fecha = datetime.datetime(2026, 11, 2, 9, 30)
    escribir_filas(hoja, [[None, 7, Decimal("12.50"), fecha, ""]])
    celdas = hoja[1]
    assert celdas[0].value is None and celdas[1].value == 7 and celdas[2].value == Decimal("12.50")
    assert celdas[3].value == fecha and celdas[3].is_date


def test_no_recorre_toda_la_hoja_por_cada_fila(monkeypatch):
    """max_row y max_column son O(celdas): usarlos por fila hacía cuadrática la exportación."""
    consultas = []
    for nombre in ("max_row", "max_column"):
        original = getattr(Worksheet, nombre)
        monkeypatch.setattr(Worksheet, nombre, property(lambda self, o=original, n=nombre: consultas.append(n) or o.fget(self)))
    hoja = _hoja()
    escribir_filas(hoja, ([f"cliente {i}", i, "=x"] for i in range(400)))
    assert consultas == []


def _guardar(libro):
    buffer = io.BytesIO()
    libro.save(buffer)
    buffer.seek(0)
    return buffer


def test_la_exportacion_de_clientes_no_recorre_la_hoja_por_cada_cliente(
    client, monkeypatch, iniciar_sesion, fake_connection_factory
):
    """Con 5.000 clientes la exportación tardaba más de 5 s solo en armar el libro; el volcado de openpyxl lo hace una vez."""
    cliente = {"id_cliente": 1, "rut": "76.543.210-9", "razon_social": "=Cliente", "estado": "ACTIVO", "telefono": None,
               "fecha_creacion": datetime.datetime(2026, 9, 1, 10), "responsables_nombres": None}

    def handler(sql, params, cursor):
        consulta = normalize_sql(sql)
        if "SELECT a.nombre_area FROM cliente_area" in consulta:
            return [{"nombre_area": "JURIDICA"}]
        if "FROM cliente c" in consulta:
            return [dict(cliente, id_cliente=i) for i in range(1, 601)]
        return []

    iniciar_sesion(rol_id=1)
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: fake_connection_factory(handler))
    consultas = []
    original = Worksheet.max_row
    monkeypatch.setattr(Worksheet, "max_row", property(lambda self: consultas.append(1) or original.fget(self)))

    respuesta = client.get("/api/clientes/listado", query_string={"formato": "excel"})

    assert respuesta.status_code == 200
    hoja = load_workbook(io.BytesIO(respuesta.data)).active
    assert hoja.max_row == 601 and hoja["B2"].data_type == "s" and hoja["B2"].value == "=Cliente"
    assert len(consultas) < 10, f"{len(consultas)} recorridos de la hoja para 600 clientes"
