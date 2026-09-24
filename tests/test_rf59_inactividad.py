# -*- coding: utf-8 -*-
"""RF59 — Cerrando Automático por Inactividad.

La sesión caduca cuando pasa más tiempo que el configurado sin actividad del
usuario; las solicitudes marcadas con `X-Actividad: pasiva` no renuevan el
plazo; el aviso del frontend puede extender la sesión y solo un administrador
cambia el tiempo máximo.
"""
import time

import pytest

import backend.routes.auth_routes as auth_routes
import backend.utils.auth as auth_module
from tests.conftest import FakeConnection, normalize_sql


@pytest.fixture(autouse=True)
def config_fija(monkeypatch):
    monkeypatch.setattr(auth_module, "obtener_config_sesion", lambda: (30, 60))


def _fijar_ultima_actividad(client, segundos_atras):
    with client.session_transaction() as sesion:
        sesion["ultima_actividad"] = time.time() - segundos_atras


def _ultima_actividad(client):
    with client.session_transaction() as sesion:
        return sesion.get("ultima_actividad")


def test_la_sesion_expira_tras_el_tiempo_de_inactividad(client, iniciar_sesion):
    iniciar_sesion(usuario_id=4, rol_id=2)
    _fijar_ultima_actividad(client, 31 * 60)

    respuesta = client.get("/api/auth/me")

    assert respuesta.status_code == 401
    assert respuesta.get_json()["codigo"] == auth_module.CODIGO_SESION_EXPIRADA
    with client.session_transaction() as sesion:
        assert "usuario_id" not in sesion

    segunda = client.get("/api/auth/me")
    assert segunda.status_code == 401
    assert "codigo" not in segunda.get_json()


def test_el_cierre_por_inactividad_queda_en_auditoria(client, monkeypatch):
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = 4
        sesion["ultima_actividad"] = time.time() - 31 * 60

    conexion = FakeConnection(lambda sql, params, cursor: [])
    monkeypatch.setattr(auth_module, "get_connection", lambda: conexion)

    assert client.get("/api/auth/me").status_code == 401

    inserciones = [params for sql, params in conexion.executed
                   if "INSERT INTO auditoria" in normalize_sql(sql)]
    assert inserciones == [(4, "sesion", 4, "CIERRE_INACTIVIDAD", None, None)]
    assert conexion.commits == 1


def test_dentro_del_plazo_la_actividad_renueva(client, iniciar_sesion):
    iniciar_sesion(usuario_id=4, rol_id=2)
    _fijar_ultima_actividad(client, 10 * 60)

    assert client.get("/api/auth/me").status_code == 200
    assert time.time() - _ultima_actividad(client) < 5


def test_una_solicitud_pasiva_no_renueva(client, iniciar_sesion):
    iniciar_sesion(usuario_id=4, rol_id=2)
    _fijar_ultima_actividad(client, 10 * 60)

    assert client.get("/api/auth/me", headers={"X-Actividad": "pasiva"}).status_code == 200
    assert time.time() - _ultima_actividad(client) >= 10 * 60 - 1


def test_estado_de_sesion_es_pasivo_aunque_falte_la_cabecera(client, iniciar_sesion):
    iniciar_sesion(usuario_id=4, rol_id=2)
    _fijar_ultima_actividad(client, 100)

    datos = client.get("/api/auth/sesion").get_json()

    assert 30 * 60 - 105 <= datos["segundos_restantes"] <= 30 * 60 - 100
    assert (datos["limite_minutos"], datos["aviso_segundos"]) == (30, 60)
    assert time.time() - _ultima_actividad(client) >= 99


def test_extender_renueva_la_sesion(client, iniciar_sesion):
    iniciar_sesion(usuario_id=4, rol_id=2)
    _fijar_ultima_actividad(client, 29 * 60)

    datos = client.post("/api/auth/sesion/extender").get_json()

    assert datos["segundos_restantes"] >= 30 * 60 - 2


def test_sin_marca_previa_se_inicializa_y_no_expira(client, iniciar_sesion):
    iniciar_sesion(usuario_id=4, rol_id=2)

    assert client.get("/api/auth/me", headers={"X-Actividad": "pasiva"}).status_code == 200
    assert _ultima_actividad(client) is not None


# ------------------------------------------------------------ configuración

@pytest.fixture
def conexion_parametros(monkeypatch):
    def handler(sql, params, cursor):
        if "SELECT valor_parametro FROM parametros_sistema" in normalize_sql(sql):
            return [{"valor_parametro": "30"}] if params[0] == auth_module.PARAMETRO_INACTIVIDAD else []
        return []

    conexion = FakeConnection(handler)
    monkeypatch.setattr(auth_routes, "get_connection", lambda: conexion)
    return conexion


def test_solo_el_administrador_cambia_el_tiempo(client, iniciar_sesion, conexion_parametros):
    iniciar_sesion(usuario_id=4, rol_id=2)

    respuesta = client.put("/api/parametros/sesion", json={"limite_minutos": 20, "aviso_segundos": 60})

    assert respuesta.status_code == 403
    assert conexion_parametros.executed == []


@pytest.mark.parametrize("cuerpo", [
    {"limite_minutos": 2, "aviso_segundos": 60},
    {"limite_minutos": 500, "aviso_segundos": 60},
    {"limite_minutos": "abc", "aviso_segundos": 60},
    {"limite_minutos": 20, "aviso_segundos": 5},
    {"limite_minutos": 5, "aviso_segundos": 300},
    {"limite_minutos": True, "aviso_segundos": 60},
])
def test_valores_invalidos_responden_400(client, iniciar_sesion, conexion_parametros, cuerpo):
    iniciar_sesion(usuario_id=1, rol_id=1)

    assert client.put("/api/parametros/sesion", json=cuerpo).status_code == 400
    assert conexion_parametros.executed == []


def test_el_administrador_guarda_la_configuracion_y_se_audita(client, iniciar_sesion, conexion_parametros):
    iniciar_sesion(usuario_id=1, rol_id=1)

    respuesta = client.put("/api/parametros/sesion", json={"limite_minutos": 20, "aviso_segundos": 90})

    assert respuesta.status_code == 200
    sentencias = [(normalize_sql(sql), params) for sql, params in conexion_parametros.executed]
    assert ("UPDATE parametros_sistema SET valor_parametro = %s WHERE nombre_parametro = %s",
            ("20", "SESION_INACTIVIDAD_MINUTOS")) in sentencias
    assert any(sql.startswith("INSERT INTO parametros_sistema") and params[0] == "SESION_AVISO_SEGUNDOS"
               for sql, params in sentencias)
    auditoria = [params for sql, params in sentencias if sql.startswith("INSERT INTO auditoria")]
    assert auditoria and auditoria[0][1:4] == ("parametros_sistema", None, "CONFIGURAR_SESION")
    assert conexion_parametros.commits == 1


def test_la_configuracion_usa_valores_por_defecto_si_no_son_validos(monkeypatch):
    monkeypatch.undo()
    auth_module.invalidar_cache_config_sesion()

    def handler(sql, params, cursor):
        return [{"valor_parametro": "1"}]  # fuera de rango

    monkeypatch.setattr(auth_module, "get_connection", lambda: FakeConnection(handler))

    assert auth_module.obtener_config_sesion() == (
        auth_module.INACTIVIDAD_MINUTOS_DEFECTO, auth_module.AVISO_SEGUNDOS_DEFECTO
    )
    auth_module.invalidar_cache_config_sesion()
