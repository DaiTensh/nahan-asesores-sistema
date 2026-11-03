# -*- coding: utf-8 -*-
"""RF15 — Asignando tareas a usuarios específicos según su área y nivel de responsabilidad.

Estas pruebas describen lo que el sistema hace hoy y NO imponen una regla nueva.
Quien asigna ve el rol y el área de cada persona y puede acotar la lista por área;
el sistema no impide asignar una tarea a alguien de otra área porque RF19 permite
«redistribuir la carga laboral entre usuarios o áreas» y la opción «Ambas áreas»
crea una tarea por área con el mismo responsable. Si el equipo decide exigir la
coincidencia de área, estas pruebas son las que deben cambiar (ver el informe de
cierre, RF15).
"""
import os

import pytest

from tests.mysql_desechable import BASE_APP, herramientas_disponibles
from tests.test_rf74_mysql_real import mundo, servidor  # noqa: F401  (fixtures compartidas)

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)

ID_ADMIN, ID_JURIDICA = 1, 2


@pytest.fixture
def contable(servidor, mundo):  # noqa: F811
    """Agrega a una persona ficticia del área contable (rol 3, área 2) y devuelve su id."""
    cn = servidor.conectar(base=BASE_APP)
    cur = cn.cursor()
    cur.execute(
        "INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) "
        "VALUES (3, 2, 'Usuario Contable Ficticio', 'contable@ejemplo.invalid', 'hash-ficticio-3')")
    cn.commit()
    id_usuario = cur.lastrowid
    cn.close()
    return id_usuario


def _crear(client, **extra):
    cuerpo = {"id_cliente": 1, "areas": [1], "id_responsable": ID_JURIDICA, "titulo": "Asignación de prueba", "prioridad": "MEDIA", **extra}
    return client.post("/api/tareas", json=cuerpo)


def test_quien_asigna_ve_el_rol_y_el_area_de_cada_persona_y_puede_acotar_por_area(client, iniciar_sesion, contable):
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)

    todos = {u["id_usuario"]: u for u in client.get("/api/usuarios", query_string={"estado": "ACTIVO"}).get_json()}
    solo_contables = client.get("/api/usuarios", query_string={"id_area": 2, "estado": "ACTIVO"}).get_json()

    assert (todos[contable]["nombre_rol"], todos[contable]["nombre_area"]) == ("USUARIO_AREA_CONTABLE", "CONTABLE")
    assert (todos[ID_JURIDICA]["nombre_rol"], todos[ID_JURIDICA]["nombre_area"]) == ("USUARIO_AREA_JURIDICA", "JURIDICA")
    assert [u["id_usuario"] for u in solo_contables] == [contable]


def test_una_persona_de_area_ve_el_area_de_los_demas_pero_no_su_rol(client, iniciar_sesion, contable):
    iniciar_sesion(usuario_id=ID_JURIDICA, rol_id=2, area_id=1)

    usuarios = {u["id_usuario"]: u for u in client.get("/api/usuarios").get_json()}

    assert usuarios[contable]["nombre_area"] == "CONTABLE" and "nombre_rol" not in usuarios[contable]


def test_hoy_se_puede_asignar_una_tarea_a_alguien_de_otra_area_y_la_tarea_conserva_la_suya(client, iniciar_sesion, mundo, contable):  # noqa: F811
    """Caracteriza el comportamiento vigente (decisión pendiente del equipo, no una regla)."""
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)

    assert _crear(client, areas=[1], id_responsable=contable).status_code == 201

    tarea = mundo.consulta("SELECT id_area, id_responsable FROM tarea ORDER BY id_tarea DESC LIMIT 1")[0]
    assert (tarea["id_area"], tarea["id_responsable"]) == (1, contable)


def test_ambas_areas_crea_una_tarea_por_area_con_el_mismo_responsable(client, iniciar_sesion, mundo, contable):  # noqa: F811
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)

    assert _crear(client, areas=[1, 2], id_responsable=ID_JURIDICA).status_code == 201

    filas = mundo.consulta("SELECT id_area, id_responsable FROM tarea ORDER BY id_tarea DESC LIMIT 2")
    assert sorted((f["id_area"], f["id_responsable"]) for f in filas) == [(1, ID_JURIDICA), (2, ID_JURIDICA)]


def test_la_redistribucion_entre_areas_deja_historial_y_no_cambia_el_area_de_la_tarea(client, iniciar_sesion, mundo, contable):  # noqa: F811
    """RF19: redistribuir «entre usuarios o áreas». RF15 no la contradice mientras no se imponga una regla."""
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    assert _crear(client, areas=[1], id_responsable=ID_JURIDICA).status_code == 201
    id_tarea = mundo.consulta("SELECT id_tarea FROM tarea ORDER BY id_tarea DESC LIMIT 1")[0]["id_tarea"]

    respuesta = client.put("/api/tareas/reasignar-masivo", json={"ids_tarea": [id_tarea], "id_responsable": contable})

    assert respuesta.status_code == 200
    tarea = mundo.consulta("SELECT id_area, id_responsable FROM tarea WHERE id_tarea = %s", (id_tarea,))[0]
    assert (tarea["id_area"], tarea["id_responsable"]) == (1, contable)
    historial = mundo.consulta("SELECT datos_anteriores, datos_nuevos FROM auditoria WHERE accion = 'REASIGNACION_MASIVA'")
    assert historial and f"id_responsable={ID_JURIDICA}" in historial[-1]["datos_anteriores"]
    assert f"id_responsable={contable}" in historial[-1]["datos_nuevos"]
