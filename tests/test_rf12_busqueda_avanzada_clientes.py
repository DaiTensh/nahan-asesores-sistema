import io

import pytest
from openpyxl import load_workbook

from tests.conftest import normalize_sql
from backend.routes import clientes_routes


URL = "/api/clientes/listado"
CLIENTE = {
    "id_cliente": 8,
    "rut": "76.543.210-9",
    "razon_social": "Comercial Andes SpA",
    "estado": "ACTIVO",
    "telefono": "+56 2 2345 6789",
    "fecha_creacion": "2026-09-01 10:00:00",
    "areas_nombres": "JURIDICA",
    "responsables_nombres": "Elías Alarcón",
}


def _handler(sql, params, cursor):
    consulta = normalize_sql(sql)
    if "SELECT a.nombre_area FROM cliente_area" in consulta:
        return [{"nombre_area": "JURIDICA"}]
    if "FROM cliente c" in consulta:
        return [CLIENTE.copy()]
    return []


def _preparar_listado(monkeypatch, iniciar_sesion, fake_connection_factory, rol_id=1):
    iniciar_sesion(rol_id=rol_id)
    conexion = fake_connection_factory(_handler)
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: conexion)
    return conexion


@pytest.mark.parametrize(
    ("filtros", "fragmento_sql", "valor"),
    [
        ({"nombre": "Andes"}, "c.razon_social LIKE %s", "%Andes%"),
        ({"rut": "76.543"}, "c.rut LIKE %s", "%76.543%"),
        ({"id_area": "2"}, "ca.id_area = %s", "2"),
        ({"estado": "INACTIVO"}, "c.estado = %s", "INACTIVO"),
        (
            {"id_responsable": "7"},
            "tr.id_responsable = %s",
            "7",
        ),
    ],
)
def test_aplica_cada_filtro_oficial(
    client, monkeypatch, iniciar_sesion, fake_connection_factory, filtros, fragmento_sql, valor
):
    conexion = _preparar_listado(monkeypatch, iniciar_sesion, fake_connection_factory)

    respuesta = client.get(URL, query_string=filtros)

    assert respuesta.status_code == 200
    consulta, parametros = conexion.executed[0]
    assert fragmento_sql in normalize_sql(consulta)
    assert valor in parametros[:-2]


def test_combina_filtros_conjuntivamente_en_una_consulta(
    client, monkeypatch, iniciar_sesion, fake_connection_factory
):
    conexion = _preparar_listado(monkeypatch, iniciar_sesion, fake_connection_factory)
    filtros = {
        "nombre": "Andes",
        "rut": "76.543",
        "id_area": "2",
        "estado": "ACTIVO",
        "id_responsable": "7",
    }

    respuesta = client.get(URL, query_string=filtros)

    assert respuesta.status_code == 200
    consulta, parametros = conexion.executed[0]
    consulta = normalize_sql(consulta)
    for fragmento in (
        "ca.id_area = %s", "c.razon_social LIKE %s", "c.rut LIKE %s",
        "c.estado = %s", "tr.id_responsable = %s",
    ):
        assert fragmento in consulta
    assert " AND ".join((
        "ca.id_area = %s", "c.razon_social LIKE %s", "c.rut LIKE %s",
        "c.estado = %s", "EXISTS (SELECT 1 FROM tarea tr WHERE tr.id_cliente = c.id_cliente AND tr.id_responsable = %s)",
    )) in consulta
    assert parametros == ("2", "%Andes%", "%76.543%", "ACTIVO", "7", 7, 0)


@pytest.mark.parametrize(
    ("orden", "direccion", "esperado"),
    [
        ("razon_social", "asc", "ORDER BY c.razon_social ASC, c.id_cliente ASC"),
        ("estado", "desc", "ORDER BY c.estado DESC, c.id_cliente ASC"),
        ("fecha_creacion", "asc", "ORDER BY c.fecha_creacion ASC, c.id_cliente ASC"),
        ("fecha_creacion", "desc", "ORDER BY c.fecha_creacion DESC, c.id_cliente ASC"),
    ],
)
def test_filtros_se_combinan_con_ordenamiento_rf62(
    client, monkeypatch, iniciar_sesion, fake_connection_factory, orden, direccion, esperado
):
    conexion = _preparar_listado(monkeypatch, iniciar_sesion, fake_connection_factory)

    respuesta = client.get(
        URL,
        query_string={"nombre": "Andes", "estado": "ACTIVO", "orden": orden, "direccion": direccion},
    )

    assert respuesta.status_code == 200
    consulta = normalize_sql(conexion.executed[0][0])
    assert "c.razon_social LIKE %s" in consulta
    assert "c.estado = %s" in consulta
    assert esperado in consulta


def test_exporta_excel_respetando_filtros_y_sin_paginacion(
    client, monkeypatch, iniciar_sesion, fake_connection_factory
):
    conexion = _preparar_listado(monkeypatch, iniciar_sesion, fake_connection_factory)

    respuesta = client.get(
        URL,
        query_string={
            "formato": "excel", "nombre": "Andes", "rut": "76.543", "id_area": "2",
            "estado": "ACTIVO", "id_responsable": "7", "orden": "estado", "direccion": "desc",
        },
    )

    assert respuesta.status_code == 200
    assert "spreadsheetml.sheet" in respuesta.mimetype
    consulta, parametros = conexion.executed[0]
    assert "LIMIT %s" not in normalize_sql(consulta)
    assert parametros == ("2", "%Andes%", "%76.543%", "ACTIVO", "7")
    filas = list(load_workbook(io.BytesIO(respuesta.data)).active.values)
    assert filas[0] == ("RUT", "Razón Social", "Áreas", "Estado", "Fecha de creación", "Responsables asignados")
    assert filas[1][0:4] == (CLIENTE["rut"], CLIENTE["razon_social"], "JURIDICA", "ACTIVO")
    assert filas[1][5] == "Elías Alarcón"


@pytest.mark.parametrize(
    "filtros",
    [
        {"id_area": "0"},
        {"id_area": "abc"},
        {"id_responsable": "-1"},
        {"id_responsable": "abc"},
        {"estado": "PENDIENTE"},
        {"formato": "csv"},
    ],
)
def test_rechaza_filtros_y_formatos_invalidos(
    client, monkeypatch, iniciar_sesion, fake_connection_factory, filtros
):
    conexion = _preparar_listado(monkeypatch, iniciar_sesion, fake_connection_factory)

    respuesta = client.get(URL, query_string=filtros)

    assert respuesta.status_code == 400
    assert conexion.executed == []


def test_conserva_autorizacion_de_roles_operativos(
    client, monkeypatch, iniciar_sesion, fake_connection_factory
):
    conexion = _preparar_listado(monkeypatch, iniciar_sesion, fake_connection_factory, rol_id=4)

    respuesta = client.get(URL, query_string={"nombre": "Andes"})

    assert respuesta.status_code == 403
    assert conexion.executed == []