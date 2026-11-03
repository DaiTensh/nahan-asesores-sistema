"""GET /api/usuarios: respuesta completa para el administrador y limitada para los demás roles.

Los usuarios operativos necesitan la lista para elegir responsables de tareas,
no para ver correos, roles ni fechas de alta.
"""
import json
import os
import re

import pytest

import backend.routes.usuarios_routes as rutas

CAMPOS_ADMIN = {"id_usuario", "id_rol", "id_area", "nombres", "email", "estado", "fecha_creacion", "nombre_rol", "nombre_area"}
CAMPOS_OPERATIVO = {"id_usuario", "nombres", "id_area", "nombre_area", "estado"}
FILA_OPERATIVA = {"id_usuario": 3, "nombres": "Ana Pérez", "id_area": 2, "nombre_area": "CONTABLE", "estado": "ACTIVO"}


def con_base(fake_connection_factory, monkeypatch, filas):
    sentencias = []

    def handler(sql, params, cursor):
        sentencias.append((" ".join(sql.split()), params))
        return [dict(f) for f in filas]
    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(rutas, "get_connection", lambda: conexion)
    return sentencias


def test_sin_sesion_responde_401(client, monkeypatch):
    monkeypatch.setattr(rutas, "get_connection", lambda: pytest.fail("no debe abrir la base"))
    assert client.get("/api/usuarios").status_code == 401


@pytest.mark.parametrize("rol_id", [2, 3])
def test_un_usuario_operativo_solo_recibe_nombre_y_area_de_las_personas_activas(client, iniciar_sesion, monkeypatch, fake_connection_factory, rol_id):
    iniciar_sesion(usuario_id=5, rol_id=rol_id, area_id=1)
    sentencias = con_base(fake_connection_factory, monkeypatch, [FILA_OPERATIVA])

    respuesta = client.get("/api/usuarios")

    assert respuesta.status_code == 200 and respuesta.get_json() == [FILA_OPERATIVA]
    consulta, parametros = sentencias[0]
    assert "SELECT u.id_usuario, u.nombres, u.id_area, a.nombre_area, u.estado" in consulta
    for sensible in ("email", "password", "fecha_creacion", "id_rol", "nombre_rol", "JOIN rol"):
        assert sensible not in consulta, sensible
    assert "WHERE u.estado = %s" in consulta and parametros == ("ACTIVO",)
    assert consulta.endswith("ORDER BY u.nombres ASC, u.id_usuario ASC")


def test_el_administrador_conserva_la_respuesta_completa(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)
    sentencias = con_base(fake_connection_factory, monkeypatch, [])
    assert client.get("/api/usuarios").status_code == 200
    consulta, parametros = sentencias[0]
    for campo in ("u.email", "u.id_rol", "u.fecha_creacion", "r.nombre_rol", "INNER JOIN rol r"):
        assert campo in consulta, campo
    assert parametros == () and consulta.endswith("ORDER BY u.id_usuario DESC")


def test_el_administrador_sigue_pudiendo_filtrar_y_ordenar(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion(usuario_id=1, rol_id=1)
    sentencias = con_base(fake_connection_factory, monkeypatch, [])
    respuesta = client.get("/api/usuarios", query_string={"id_rol": 2, "estado": "inactivo", "ordenar_por": "fecha_registro", "direccion": "asc"})
    assert respuesta.status_code == 200
    consulta, parametros = sentencias[0]
    assert "u.id_rol = %s" in consulta and "u.estado = %s" in consulta and "ORDER BY u.fecha_creacion ASC" in consulta
    assert parametros == (2, "INACTIVO")


@pytest.mark.parametrize("rol_id", [2, 3])
def test_un_usuario_operativo_no_puede_filtrar_por_rol(client, iniciar_sesion, monkeypatch, rol_id):
    """El filtro por rol permitiría deducir quiénes son administradores aunque el rol no se muestre."""
    iniciar_sesion(usuario_id=5, rol_id=rol_id)
    monkeypatch.setattr(rutas, "get_connection", lambda: pytest.fail("no debe abrir la base"))
    respuesta = client.get("/api/usuarios", query_string={"id_rol": 1})
    assert respuesta.status_code == 403 and "rol" in respuesta.get_json()["error"]


def test_un_usuario_operativo_no_ve_personas_inactivas(client, iniciar_sesion, monkeypatch):
    iniciar_sesion(usuario_id=5, rol_id=2)
    monkeypatch.setattr(rutas, "get_connection", lambda: pytest.fail("no debe abrir la base"))
    respuesta = client.get("/api/usuarios", query_string={"estado": "INACTIVO"})
    assert respuesta.status_code == 200 and respuesta.get_json() == []


def test_un_usuario_operativo_no_obtiene_el_orden_por_fecha_de_registro(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion(usuario_id=5, rol_id=3)
    sentencias = con_base(fake_connection_factory, monkeypatch, [])
    assert client.get("/api/usuarios", query_string={"ordenar_por": "fecha_registro", "direccion": "DESC"}).status_code == 200
    assert "fecha_creacion" not in sentencias[0][0] and sentencias[0][0].endswith("ORDER BY u.nombres ASC, u.id_usuario ASC")


@pytest.mark.parametrize("parametros", [{"id_area": "x"}, {"id_area": 0}, {"estado": "BORRADO"}, {"id_rol": "x"}])
def test_los_parametros_invalidos_se_siguen_rechazando_con_400(client, iniciar_sesion, monkeypatch, parametros):
    iniciar_sesion(usuario_id=5, rol_id=2)
    monkeypatch.setattr(rutas, "get_connection", lambda: pytest.fail("no debe abrir la base"))
    assert client.get("/api/usuarios", query_string=parametros).status_code == 400


def test_el_filtro_por_area_sigue_disponible_para_el_usuario_operativo(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion(usuario_id=5, rol_id=2)
    sentencias = con_base(fake_connection_factory, monkeypatch, [FILA_OPERATIVA])
    assert client.get("/api/usuarios", query_string={"id_area": 2}).status_code == 200
    assert sentencias[0][1] == (2, "ACTIVO")


# --- consumidores del frontend -------------------------------------------------

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def leer(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as archivo:
        return archivo.read()


def test_el_dashboard_oculta_y_no_pide_lo_que_solo_ve_el_administrador():
    html = leer("frontend", "dashboard", "dashboard.html")
    js = leer("frontend", "dashboard", "dashboard.js")
    assert html.count("data-solo-admin") == 7, "4 tarjetas de usuarios y 3 secciones"
    for titulo in ("Distribución por área", "Carga de trabajo por usuario", "Usuarios registrados"):
        assert re.search(rf'<section class="dashboard-section" data-solo-admin>\s*<h2>{titulo}</h2>', html), titulo
    assert re.search(r"if \(esAdministrador\) \{\s*cargarResumenUsuarios\(\);\s*cargarCargaTrabajoPorUsuario\(\);", js)
    assert "if (esAdministrador) cargarDistribucionPorArea();" in js
    assert "bloque.hidden = true" in js


def test_el_autocompletado_no_depende_del_correo_ni_del_rol():
    js = leer("frontend", "assets", "js", "usuarios_autocomplete.js")
    assert "usuario.email || nombreArea(usuario)" in js
    assert 'ADMINISTRACION: "Administración"' in js, "el área se muestra con tilde"
    assert ".filter(Boolean).join" in js, "la etiqueta omite lo que no llega"
    assert "(n.º ${usuario.id_usuario})" in js, "los homónimos se distinguen por número"
