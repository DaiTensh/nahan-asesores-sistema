"""RF74 — Definiendo la tarifa por hora (API de administración, sin MySQL)."""
import pytest

import backend.routes.tarifas_routes as rutas
from backend.routes.tarifas_routes import leer_valor_hora

ENDPOINTS = [
    ("get", "/api/tarifas", None),
    ("put", "/api/tarifas/general", {"valor_hora": 40000}),
    ("put", "/api/tarifas/areas/1", {"valor_hora": 40000}),
    ("delete", "/api/tarifas/areas/1", None),
]


def llamar(client, metodo, ruta, cuerpo):
    return getattr(client, metodo)(ruta, **({"json": cuerpo} if cuerpo is not None else {}))


@pytest.mark.parametrize("metodo,ruta,cuerpo", ENDPOINTS)
def test_sin_sesion_responde_401(client, monkeypatch, metodo, ruta, cuerpo):
    monkeypatch.setattr(rutas, "get_connection", lambda: pytest.fail("no debe abrir la base"))
    assert llamar(client, metodo, ruta, cuerpo).status_code == 401


@pytest.mark.parametrize("rol_id", [2, 3])
@pytest.mark.parametrize("metodo,ruta,cuerpo", ENDPOINTS)
def test_un_usuario_operativo_recibe_403(client, iniciar_sesion, monkeypatch, rol_id, metodo, ruta, cuerpo):
    monkeypatch.setattr(rutas, "get_connection", lambda: pytest.fail("no debe abrir la base"))
    iniciar_sesion(usuario_id=5, rol_id=rol_id, area_id=1)
    assert llamar(client, metodo, ruta, cuerpo).status_code == 403


@pytest.mark.parametrize("valor", [40000, 40000.5, "40000", "40000.50", " 40000 ", "0.01", "10000000", 1, "99999.99"])
def test_montos_validos(valor):
    assert leer_valor_hora(valor) is not None


@pytest.mark.parametrize("valor", [0, -1, "-5", "0", "0.00", "abc", "", None, True, False, [], {}, "1e5", "10000000.01", "10000001",
                                   "40000.123", "4 0000", "40.000,5", "١٢٣", float("nan"), float("inf"), 1e12, "99999999.99", "NaN", "Infinity"])
def test_montos_invalidos(valor):
    assert leer_valor_hora(valor) is None


@pytest.mark.parametrize("ruta", ["/api/tarifas/general", "/api/tarifas/areas/1"])
@pytest.mark.parametrize("cuerpo", [None, [], "x", {}, {"valor_hora": 0}, {"valor_hora": "abc"}, {"valor_hora": True}, {"valor_hora": 20000000}])
def test_un_valor_invalido_se_rechaza_sin_tocar_la_base(client, iniciar_sesion, monkeypatch, ruta, cuerpo):
    iniciar_sesion(usuario_id=1, rol_id=1)
    monkeypatch.setattr(rutas, "get_connection", lambda: pytest.fail("no debe abrir la base"))
    respuesta = client.put(ruta, json=cuerpo) if cuerpo is not None else client.put(ruta)
    assert respuesta.status_code == 400
    assert "tarifa" in respuesta.get_json()["error"].lower() or "objeto JSON" in respuesta.get_json()["error"]


def conexion_con(fake_connection_factory, monkeypatch, handler):
    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(rutas, "get_connection", lambda: conexion)
    return conexion


def sentencias(conexion):
    return [(" ".join(sql.split()), params) for sql, params in conexion.executed]


def test_definir_la_tarifa_general_actualiza_el_parametro_y_audita(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion(usuario_id=7, rol_id=1)
    conexion = conexion_con(fake_connection_factory, monkeypatch,
                            lambda sql, p, c: [{"valor_parametro": "30000.00"}] if sql.lstrip().startswith("SELECT valor_parametro") else [])
    respuesta = client.put("/api/tarifas/general", json={"valor_hora": 45000.5})
    assert respuesta.status_code == 200 and respuesta.get_json()["valor_hora"] == 45000.5
    ejecutadas = sentencias(conexion)
    assert ("UPDATE parametros_sistema SET valor_parametro = %s WHERE nombre_parametro = %s", ("45000.50", "TARIFA_HORA_DEFAULT")) in ejecutadas
    auditoria = [p for s, p in ejecutadas if s.startswith("INSERT INTO auditoria")]
    assert auditoria == [(7, "parametros_sistema", None, "CONFIGURAR_TARIFA_GENERAL",
                          "TARIFA_HORA_DEFAULT=30000.00", "TARIFA_HORA_DEFAULT=45000.50")]
    assert conexion.commits == 1


def test_si_el_parametro_no_existia_se_crea(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion(usuario_id=7, rol_id=1)
    conexion = conexion_con(fake_connection_factory, monkeypatch, lambda sql, p, c: [])
    assert client.put("/api/tarifas/general", json={"valor_hora": "35000"}).status_code == 200
    insercion = [(s, p) for s, p in sentencias(conexion) if s.startswith("INSERT INTO parametros_sistema")]
    assert len(insercion) == 1 and insercion[0][1] == ("TARIFA_HORA_DEFAULT", "35000.00")


def test_definir_la_tarifa_de_un_area_cierra_la_anterior_e_inserta_la_nueva(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion(usuario_id=7, rol_id=1)

    def handler(sql, params, cursor):
        if sql.lstrip().startswith("SELECT id_area FROM area"):
            return [{"id_area": 2}]
        if "FROM tarifa_hora t2" in sql:
            return [{"id_tarifa": 4, "valor_hora": "30000.00"}]
        if "valor_parametro" in sql:
            return [{"valor_parametro": "CLP"}]
        cursor.lastrowid = 9
        return []
    conexion = conexion_con(fake_connection_factory, monkeypatch, handler)
    respuesta = client.put("/api/tarifas/areas/2", json={"valor_hora": 38000})
    assert respuesta.status_code == 200
    ejecutadas = sentencias(conexion)
    posicion = lambda prefijo: next(i for i, (sql, _) in enumerate(ejecutadas) if sql.startswith(prefijo))
    assert posicion("UPDATE tarifa_hora SET estado = 'INACTIVA'") < posicion("INSERT INTO tarifa_hora")
    insercion = next(p for s, p in ejecutadas if s.startswith("INSERT INTO tarifa_hora"))
    assert insercion == (2, "38000.00", "CLP")
    auditoria = next(p for s, p in ejecutadas if s.startswith("INSERT INTO auditoria"))
    assert auditoria == (7, "tarifa_hora", 9, "TARIFA_AREA_DEFINIDA", "id_area=2, valor_hora=30000.00", "id_area=2, valor_hora=38000.00")
    assert conexion.commits == 1 and conexion.rollbacks == 0


def test_tarifa_de_un_area_inexistente_responde_404(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion(usuario_id=7, rol_id=1)
    conexion = conexion_con(fake_connection_factory, monkeypatch, lambda sql, p, c: [])
    assert client.put("/api/tarifas/areas/99", json={"valor_hora": 100}).status_code == 404
    assert conexion.commits == 0 and not [s for s, _ in sentencias(conexion) if s.startswith(("INSERT", "UPDATE"))]


def test_quitar_la_tarifa_de_un_area_sin_tarifa_propia_responde_404(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion(usuario_id=7, rol_id=1)
    conexion = conexion_con(fake_connection_factory, monkeypatch, lambda sql, p, c: [])
    respuesta = client.delete("/api/tarifas/areas/2")
    assert respuesta.status_code == 404 and "tarifa general" in respuesta.get_json()["error"]
    assert conexion.commits == 0


def test_quitar_la_tarifa_de_un_area_conserva_el_historial_y_audita(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion(usuario_id=7, rol_id=1)
    conexion = conexion_con(fake_connection_factory, monkeypatch,
                            lambda sql, p, c: [{"id_tarifa": 4, "valor_hora": "30000.00"}] if "FROM tarifa_hora t2" in sql else [])
    respuesta = client.delete("/api/tarifas/areas/2")
    assert respuesta.status_code == 200
    ejecutadas = sentencias(conexion)
    assert any(s.startswith("UPDATE tarifa_hora SET estado = 'INACTIVA'") for s, _ in ejecutadas)
    assert not any(s.startswith("DELETE") for s, _ in ejecutadas), "el historial no se borra"
    auditoria = next(p for s, p in ejecutadas if s.startswith("INSERT INTO auditoria"))
    assert auditoria[1:4] == ("tarifa_hora", 4, "TARIFA_AREA_ELIMINADA")


def test_un_fallo_de_base_hace_rollback_y_no_filtra_detalles(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion(usuario_id=7, rol_id=1)

    def handler(sql, params, cursor):
        if sql.startswith("UPDATE parametros_sistema"):
            raise RuntimeError("detalle interno secreto")
        return [{"valor_parametro": "1"}]
    conexion = conexion_con(fake_connection_factory, monkeypatch, handler)
    respuesta = client.put("/api/tarifas/general", json={"valor_hora": 100})
    assert respuesta.status_code == 500 and "secreto" not in respuesta.get_data(as_text=True)
    assert conexion.rollbacks == 1 and conexion.commits == 0


def test_obtener_tarifas_resume_general_y_areas(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    import datetime
    iniciar_sesion(usuario_id=7, rol_id=1)

    def handler(sql, params, cursor):
        if "FROM area a" in sql:
            return [{"id_area": 1, "nombre_area": "JURIDICA", "id_tarifa": 3, "valor_hora": "38000.00", "fecha_inicio": datetime.date(2026, 11, 2)},
                    {"id_area": 2, "nombre_area": "CONTABLE", "id_tarifa": None, "valor_hora": None, "fecha_inicio": None}]
        return [{"valor_parametro": "CLP" if "MONEDA" in str(params) else "30000.00"}]
    conexion_con(fake_connection_factory, monkeypatch, handler)
    cuerpo = client.get("/api/tarifas").get_json()
    assert cuerpo["general"] == {"valor_hora": 30000.0, "moneda": "CLP"}
    assert cuerpo["areas"][0] == {"id_area": 1, "nombre_area": "JURIDICA", "valor_hora": 38000.0, "vigente_desde": "2026-11-02", "tarifa_aplicada": 38000.0}
    assert cuerpo["areas"][1]["valor_hora"] is None and cuerpo["areas"][1]["tarifa_aplicada"] == 30000.0
