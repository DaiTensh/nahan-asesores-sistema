# -*- coding: utf-8 -*-
"""RF10 — Cambiando el Estado de Clientes.

POST /api/clientes/<id>/cambiar-estado pasa un cliente entre ACTIVO e INACTIVO
manteniendo la trazabilidad (evento CAMBIO_ESTADO con el estado anterior y el
nuevo). Solo el administrador. Hasta ahora el requisito solo se había verificado a
mano en el navegador: estas pruebas son su evidencia automatizada.
"""
import pytest

import backend.routes.clientes_routes as clientes_routes
from tests.conftest import normalize_sql


def _url(id_cliente=4):
    return f"/api/clientes/{id_cliente}/cambiar-estado"


@pytest.fixture
def preparar(client, monkeypatch, iniciar_sesion, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)

    def _preparar(estado_actual="ACTIVO", existe=True, falla_en=None):
        def handler(sql, params, cursor):
            sql_n = normalize_sql(sql)
            if sql_n.startswith("SELECT estado FROM cliente"):
                return [(estado_actual,)] if existe else []
            if falla_en and sql_n.startswith(falla_en):
                raise RuntimeError("detalle interno que no debe llegar al usuario")
            return []
        conexion = fake_connection_factory(handler)
        monkeypatch.setattr(clientes_routes, "get_connection", lambda: conexion)
        return conexion
    return _preparar


def _sentencias(conexion, comienzo):
    return [(normalize_sql(s), p) for s, p in conexion.executed if normalize_sql(s).startswith(comienzo)]


def test_el_administrador_inactiva_a_un_cliente_y_queda_el_evento(client, preparar):
    conexion = preparar("ACTIVO")

    respuesta = client.post(_url(), json={"nuevo_estado": "INACTIVO"})

    assert respuesta.status_code == 200 and "INACTIVO" in respuesta.get_json()["message"]
    assert _sentencias(conexion, "UPDATE cliente SET estado")[0][1] == ("INACTIVO", 4)
    _, parametros = _sentencias(conexion, "INSERT INTO auditoria")[0]
    assert parametros == (1, "cliente", 4, "CAMBIO_ESTADO", "estado: ACTIVO", "estado: INACTIVO")
    assert conexion.commits == 1 and conexion.rollbacks == 0 and conexion.closed


def test_tambien_se_puede_reactivar_y_acepta_minusculas(client, preparar):
    conexion = preparar("INACTIVO")

    respuesta = client.post(_url(), json={"nuevo_estado": " activo "})

    assert respuesta.status_code == 200
    assert _sentencias(conexion, "UPDATE cliente SET estado")[0][1] == ("ACTIVO", 4)
    assert _sentencias(conexion, "INSERT INTO auditoria")[0][1][4:] == ("estado: INACTIVO", "estado: ACTIVO")


def test_pedir_el_mismo_estado_se_rechaza_sin_modificar_ni_auditar(client, preparar):
    conexion = preparar("ACTIVO")

    respuesta = client.post(_url(), json={"nuevo_estado": "ACTIVO"})

    assert respuesta.status_code == 400 and "ya posee el estado ACTIVO" in respuesta.get_json()["error"]
    assert not _sentencias(conexion, "UPDATE") and not _sentencias(conexion, "INSERT INTO auditoria")
    assert conexion.commits == 0


@pytest.mark.parametrize("cuerpo", [{"nuevo_estado": "PENDIENTE"}, {"nuevo_estado": ""}, {"nuevo_estado": None}, {}])
def test_un_estado_que_no_existe_se_rechaza_sin_tocar_la_base(client, preparar, cuerpo):
    conexion = preparar()

    respuesta = client.post(_url(), json=cuerpo)

    assert respuesta.status_code == 400
    assert not conexion.executed


def test_un_cliente_inexistente_responde_404(client, preparar):
    conexion = preparar(existe=False)

    respuesta = client.post(_url(999), json={"nuevo_estado": "INACTIVO"})

    assert respuesta.status_code == 404
    assert not _sentencias(conexion, "UPDATE")


@pytest.mark.parametrize("rol_id", [2, 3])
def test_un_usuario_de_area_no_puede_cambiar_el_estado(client, iniciar_sesion, rol_id):
    iniciar_sesion(usuario_id=2, rol_id=rol_id)
    assert client.post(_url(), json={"nuevo_estado": "INACTIVO"}).status_code == 403


def test_sin_sesion_se_rechaza(client):
    assert client.post(_url(), json={"nuevo_estado": "INACTIVO"}).status_code == 401


@pytest.mark.parametrize("enviar", [
    lambda c: c.post(_url(), data="", content_type="application/json"),
    lambda c: c.post(_url(), data="{no es json", content_type="application/json"),
    lambda c: c.post(_url()),
])
def test_un_cuerpo_vacio_o_malformado_es_un_error_del_cliente_no_del_servidor(client, preparar, enviar):
    conexion = preparar()

    respuesta = enviar(client)

    assert respuesta.status_code in (400, 415), respuesta.get_json()
    assert not _sentencias(conexion, "UPDATE")


def test_si_falla_la_actualizacion_se_revierte_y_no_se_filtra_el_detalle(client, preparar):
    conexion = preparar("ACTIVO", falla_en="UPDATE cliente SET estado")

    respuesta = client.post(_url(), json={"nuevo_estado": "INACTIVO"})

    assert respuesta.status_code == 500
    assert "detalle interno" not in respuesta.get_data(as_text=True)
    assert conexion.rollbacks == 1 and conexion.commits == 0 and conexion.closed
