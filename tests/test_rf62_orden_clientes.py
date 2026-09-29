import pytest

from backend.routes import clientes_routes


def test_rf62_orden_por_defecto(client, iniciar_sesion, fake_connection_factory, monkeypatch):
    """Verifica el orden por defecto y que fecha_creacion esté en el SELECT."""
    iniciar_sesion()
    fake_conn = fake_connection_factory(lambda sql, params, cursor: [])
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: fake_conn)

    response = client.get("/api/clientes/listado")

    assert response.status_code == 200
    sql_ejecutado = fake_conn.executed[0][0]
    assert "ORDER BY c.razon_social ASC, c.id_cliente ASC" in sql_ejecutado
    assert "c.fecha_creacion" in sql_ejecutado


@pytest.mark.parametrize(
    "orden, direccion, esperado",
    [
        ("razon_social", "asc", "ORDER BY c.razon_social ASC, c.id_cliente ASC"),
        ("razon_social", "desc", "ORDER BY c.razon_social DESC, c.id_cliente ASC"),
        ("estado", "asc", "ORDER BY c.estado ASC, c.id_cliente ASC"),
        ("estado", "desc", "ORDER BY c.estado DESC, c.id_cliente ASC"),
        ("fecha_creacion", "asc", "ORDER BY c.fecha_creacion ASC, c.id_cliente ASC"),
        ("fecha_creacion", "desc", "ORDER BY c.fecha_creacion DESC, c.id_cliente ASC"),
    ],
)
def test_rf62_ordenes_validos(
    client,
    iniciar_sesion,
    fake_connection_factory,
    monkeypatch,
    orden,
    direccion,
    esperado,
):
    """Verifica las combinaciones válidas de columna y dirección."""
    iniciar_sesion()
    fake_conn = fake_connection_factory(lambda sql, params, cursor: [])
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: fake_conn)

    response = client.get(
        "/api/clientes/listado",
        query_string={"orden": orden, "direccion": direccion},
    )

    assert response.status_code == 200
    sql_ejecutado = fake_conn.executed[0][0]
    assert esperado in sql_ejecutado


@pytest.mark.parametrize(
    "query_string",
    [
        {"orden": "rut"},
        {"direccion": "arriba"},
        {"orden": "razon_social; DROP TABLE cliente"},
        {"direccion": "asc; DROP TABLE cliente"},
    ],
)
def test_rf62_parametros_invalidos_y_sql_injection(
    client, iniciar_sesion, query_string
):
    """Rechaza columnas/direcciones no permitidas e intentos de inyección."""
    iniciar_sesion()

    response = client.get("/api/clientes/listado", query_string=query_string)

    assert response.status_code == 400


def test_rf62_orden_con_filtros(
    client, iniciar_sesion, fake_connection_factory, monkeypatch
):
    """Verifica que el ordenamiento convive con los filtros existentes."""
    iniciar_sesion()
    fake_conn = fake_connection_factory(lambda sql, params, cursor: [])
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: fake_conn)

    response = client.get(
        "/api/clientes/listado",
        query_string={
            "id_area": "2",
            "buscar": "empresa",
            "orden": "estado",
            "direccion": "desc",
        },
    )

    assert response.status_code == 200
    sql_ejecutado = fake_conn.executed[0][0]
    assert "ca.id_area = %s" in sql_ejecutado
    assert "c.razon_social LIKE %s" in sql_ejecutado
    assert "ORDER BY c.estado DESC, c.id_cliente ASC" in sql_ejecutado


def test_rf62_sin_sesion(client):
    """Verifica que el endpoint sigue protegido cuando no hay sesión."""
    response = client.get("/api/clientes/listado?orden=fecha_creacion")

    assert response.status_code in (401, 403)