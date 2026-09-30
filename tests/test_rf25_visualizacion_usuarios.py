import re

import pytest

from backend.routes import usuarios_routes
from conftest import normalize_sql


USUARIOS = [
    {
        "id_usuario": 1,
        "id_rol": 1,
        "id_area": 3,
        "nombres": "Carlos Admin",
        "email": "carlos@example.test",
        "estado": "ACTIVO",
        "fecha_creacion": "2026-09-01 09:00:00",
        "nombre_rol": "ADMINISTRADOR",
        "nombre_area": "Administración",
    },
    {
        "id_usuario": 2,
        "id_rol": 2,
        "id_area": 1,
        "nombres": "Ana Pérez",
        "email": "ana@example.test",
        "estado": "ACTIVO",
        "fecha_creacion": "2026-09-03 09:00:00",
        "nombre_rol": "USUARIO_AREA_JURIDICA",
        "nombre_area": "Jurídica",
    },
    {
        "id_usuario": 3,
        "id_rol": 2,
        "id_area": 1,
        "nombres": "Beatriz Pérez",
        "email": "beatriz@example.test",
        "estado": "INACTIVO",
        "fecha_creacion": "2026-09-02 09:00:00",
        "nombre_rol": "USUARIO_AREA_JURIDICA",
        "nombre_area": "Jurídica",
    },
    {
        "id_usuario": 4,
        "id_rol": 3,
        "id_area": 2,
        "nombres": "Diego Contable",
        "email": "diego@example.test",
        "estado": "ACTIVO",
        "fecha_creacion": "2026-09-04 09:00:00",
        "nombre_rol": "USUARIO_AREA_CONTABLE",
        "nombre_area": "Contabilidad",
    },
]


@pytest.fixture
def usuarios_db(fake_connection_factory, monkeypatch):
    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "FROM usuario u" not in normalized:
            return []

        resultado = [usuario.copy() for usuario in USUARIOS]
        if "u.id_usuario = %s" in normalized:
            return [usuario for usuario in resultado if usuario["id_usuario"] == params[0]]

        indice_parametro = 0
        for columna, campo in (
            ("u.id_rol = %s", "id_rol"),
            ("u.id_area = %s", "id_area"),
            ("u.estado = %s", "estado"),
        ):
            if columna in normalized:
                valor = params[indice_parametro]
                resultado = [usuario for usuario in resultado if usuario[campo] == valor]
                indice_parametro += 1

        orden = re.search(r"ORDER BY (u\.nombres|u\.fecha_creacion) (ASC|DESC)", normalized)
        if orden:
            campo = "nombres" if orden.group(1) == "u.nombres" else "fecha_creacion"
            resultado.sort(key=lambda usuario: usuario[campo], reverse=orden.group(2) == "DESC")
        return resultado

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(usuarios_routes, "get_connection", lambda: connection)
    return connection


def test_rf25_listado_incluye_campos_requeridos(client, iniciar_sesion, usuarios_db):
    iniciar_sesion()

    response = client.get("/api/usuarios")
    datos = response.get_json()

    assert response.status_code == 200
    assert len(datos) == 4
    assert {
        "nombres", "email", "nombre_rol", "nombre_area", "estado", "fecha_creacion"
    } <= datos[0].keys()


def test_rf25_listado_vacio_y_conserva_usuarios_inactivos(client, iniciar_sesion, usuarios_db):
    iniciar_sesion()

    response = client.get("/api/usuarios?estado=INACTIVO")

    assert response.status_code == 200
    assert [usuario["estado"] for usuario in response.get_json()] == ["INACTIVO"]

    usuarios_db.handler = lambda sql, params, cursor: []
    response_vacio = client.get("/api/usuarios")
    assert response_vacio.status_code == 200
    assert response_vacio.get_json() == []


@pytest.mark.parametrize(
    ("query", "esperados"),
    [
        ("id_rol=2", [2, 3]),
        ("id_area=2", [4]),
        ("estado=ACTIVO", [1, 2, 4]),
        ("id_rol=2&id_area=1&estado=INACTIVO", [3]),
    ],
)
def test_rf25_filtros_individuales_y_combinados(
    client, iniciar_sesion, usuarios_db, query, esperados
):
    iniciar_sesion()

    response = client.get(f"/api/usuarios?{query}")

    assert response.status_code == 200
    assert [usuario["id_usuario"] for usuario in response.get_json()] == esperados


def test_rf25_orden_por_nombre_y_fecha_registro(client, iniciar_sesion, usuarios_db):
    iniciar_sesion()

    por_nombre = client.get("/api/usuarios?ordenar_por=nombre&direccion=ASC").get_json()
    por_nombre_desc = client.get("/api/usuarios?ordenar_por=nombre&direccion=DESC").get_json()
    por_fecha = client.get("/api/usuarios?ordenar_por=fecha_registro&direccion=ASC").get_json()
    por_fecha_desc = client.get("/api/usuarios?ordenar_por=fecha_registro&direccion=DESC").get_json()

    assert [usuario["nombres"] for usuario in por_nombre] == sorted(
        usuario["nombres"] for usuario in USUARIOS
    )
    assert [usuario["nombres"] for usuario in por_nombre_desc] == sorted(
        (usuario["nombres"] for usuario in USUARIOS), reverse=True
    )
    assert [usuario["id_usuario"] for usuario in por_fecha] == [1, 3, 2, 4]
    assert [usuario["id_usuario"] for usuario in por_fecha_desc] == [4, 2, 3, 1]


@pytest.mark.parametrize(
    "query",
    [
        "ordenar_por=nombres%20DESC%3B%20DROP%20TABLE%20usuario",
        "ordenar_por=correo",
        "ordenar_por=nombre&direccion=SIDEWAYS",
    ],
)
def test_rf25_rechaza_ordenamiento_invalido(client, iniciar_sesion, usuarios_db, query):
    iniciar_sesion()

    response = client.get(f"/api/usuarios?{query}")

    assert response.status_code == 400
    assert "ordenamiento" in response.get_json()["error"] or "dirección" in response.get_json()["error"]


def test_rf25_perfil_existente_e_inexistente(client, iniciar_sesion, usuarios_db):
    iniciar_sesion()

    existente = client.get("/api/usuarios/2")
    inexistente = client.get("/api/usuarios/999")

    assert existente.status_code == 200
    assert existente.get_json()["fecha_creacion"] == "2026-09-03 09:00:00"
    assert existente.get_json()["nombre_rol"] == "USUARIO_AREA_JURIDICA"
    assert inexistente.status_code == 404


def test_rf25_respeta_autorizacion_existente(client, iniciar_sesion, usuarios_db):
    response_sin_sesion = client.get("/api/usuarios")
    assert response_sin_sesion.status_code == 401

    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)
    assert client.get("/api/usuarios").status_code == 200
    assert client.get("/api/usuarios/2").status_code == 403