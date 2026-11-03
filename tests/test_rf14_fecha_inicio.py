# -*- coding: utf-8 -*-
"""RF14 — Creando Nuevas Tareas: fecha de inicio y fecha límite.

El texto oficial incluye ambas fechas entre los datos de la tarea. La fecha de
inicio reutiliza la columna `tarea.fecha_inicio`, que existe desde v1.0.0 y la
aplicación no usaba. Es opcional, igual que la fecha de vencimiento, de modo que
las tareas anteriores (con la columna en NULL) siguen siendo válidas. Se prueba
contra un MySQL real y desechable porque la columna es DATETIME.
"""
import os

import pytest

from tests.mysql_desechable import herramientas_disponibles
from tests.test_rf74_mysql_real import mundo, servidor  # noqa: F401  (fixtures compartidas)

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)

BASE = {"id_cliente": 1, "areas": [1], "id_responsable": 1, "titulo": "Declaración anual", "prioridad": "MEDIA"}


@pytest.fixture
def admin(client, iniciar_sesion, mundo):  # noqa: F811
    iniciar_sesion(usuario_id=1, rol_id=1)
    return client


def _crear(client, **extra):
    return client.post("/api/tareas", json={**BASE, **extra})


def _ultima(mundo):  # noqa: F811
    return mundo.consulta("SELECT * FROM tarea ORDER BY id_tarea DESC LIMIT 1")[0]


def test_una_tarea_se_crea_con_fecha_de_inicio_y_fecha_limite(admin, mundo):  # noqa: F811
    respuesta = _crear(admin, fecha_inicio="2026-12-01", fecha_vencimiento="2026-12-15")

    assert respuesta.status_code == 201
    tarea = _ultima(mundo)
    assert (tarea["fecha_inicio"].date().isoformat(), tarea["fecha_vencimiento"].isoformat()) == ("2026-12-01", "2026-12-15")
    detalle = admin.get(f"/api/tareas/{tarea['id_tarea']}").get_json()
    assert "01 Dec 2026" in detalle["fecha_inicio"] and "15 Dec 2026" in detalle["fecha_vencimiento"]
    evento = mundo.consulta("SELECT datos_nuevos FROM auditoria WHERE accion = 'TAREA_CREADA' ORDER BY id_auditoria DESC LIMIT 1")[0]
    assert evento["datos_nuevos"].endswith("estado=PENDIENTE, fecha_inicio=2026-12-01")


def test_sin_fecha_de_inicio_la_tarea_se_crea_igual_como_antes(admin, mundo):  # noqa: F811
    respuesta = _crear(admin, fecha_vencimiento="2026-12-15")

    assert respuesta.status_code == 201
    assert _ultima(mundo)["fecha_inicio"] is None
    evento = mundo.consulta("SELECT datos_nuevos FROM auditoria WHERE accion = 'TAREA_CREADA' ORDER BY id_auditoria DESC LIMIT 1")[0]
    assert "fecha_inicio" not in evento["datos_nuevos"], "el texto del evento no cambia para quien no la envía"


@pytest.mark.parametrize("extra,mensaje", [
    ({"fecha_inicio": "2026-12-20", "fecha_vencimiento": "2026-12-15"}, "no puede ser posterior"),
    ({"fecha_inicio": "01-12-2026"}, "fecha de inicio no es válida"),
    ({"fecha_inicio": "2026-02-30"}, "fecha de inicio no es válida"),
    ({"fecha_inicio": 20261201}, "fecha_inicio debe ser texto"),
    ({"fecha_vencimiento": 5}, "fecha_vencimiento debe ser texto"),
])
def test_las_fechas_incoherentes_o_mal_formadas_se_rechazan_sin_crear_nada(admin, mundo, extra, mensaje):  # noqa: F811
    antes = mundo.consulta("SELECT COUNT(*) AS n FROM tarea")[0]["n"]

    respuesta = _crear(admin, **extra)

    assert respuesta.status_code == 400 and mensaje in respuesta.get_json()["error"]
    assert mundo.consulta("SELECT COUNT(*) AS n FROM tarea")[0]["n"] == antes


def test_inicio_y_vencimiento_el_mismo_dia_es_valido(admin, mundo):  # noqa: F811
    assert _crear(admin, fecha_inicio="2026-12-10", fecha_vencimiento="2026-12-10").status_code == 201


def test_la_opcion_ambas_areas_aplica_la_misma_fecha_a_las_dos_tareas(admin, mundo):  # noqa: F811
    assert _crear(admin, areas=[1, 2], fecha_inicio="2026-12-01").status_code == 201

    filas = mundo.consulta("SELECT id_area, fecha_inicio FROM tarea ORDER BY id_tarea DESC LIMIT 2")
    assert sorted(f["id_area"] for f in filas) == [1, 2]
    assert {f["fecha_inicio"].date().isoformat() for f in filas} == {"2026-12-01"}


# ---------------------------------------------------------------------------
# Edición (RF64): la fecha de inicio se puede corregir, conservar o quitar
# ---------------------------------------------------------------------------

def _editar(client, id_tarea, **extra):
    cuerpo = {"titulo": "Declaración anual", "id_responsable": 1, "prioridad": "MEDIA", "fecha_vencimiento": "2026-12-31", **extra}
    return client.put(f"/api/tareas/{id_tarea}", json=cuerpo)


@pytest.fixture
def tarea(admin, mundo):  # noqa: F811
    _crear(admin, fecha_inicio="2026-12-01", fecha_vencimiento="2026-12-31")
    return _ultima(mundo)["id_tarea"]


def test_editar_permite_cambiar_la_fecha_de_inicio_y_deja_el_evento(admin, mundo, tarea):  # noqa: F811
    respuesta = _editar(admin, tarea, fecha_inicio="2026-12-05")

    assert respuesta.status_code == 200
    assert mundo.consulta("SELECT fecha_inicio FROM tarea WHERE id_tarea = %s", (tarea,))[0]["fecha_inicio"].date().isoformat() == "2026-12-05"
    evento = mundo.consulta("SELECT datos_anteriores, datos_nuevos FROM auditoria WHERE accion = 'EDICION' ORDER BY id_auditoria DESC LIMIT 1")[0]
    assert (evento["datos_anteriores"], evento["datos_nuevos"]) == (f"id_tarea={tarea}, fecha_inicio=2026-12-01", f"id_tarea={tarea}, fecha_inicio=2026-12-05")


def test_editar_sin_enviar_la_fecha_de_inicio_la_conserva(admin, mundo, tarea):  # noqa: F811
    assert _editar(admin, tarea, titulo="Otro título").status_code == 200

    assert mundo.consulta("SELECT fecha_inicio FROM tarea WHERE id_tarea = %s", (tarea,))[0]["fecha_inicio"].date().isoformat() == "2026-12-01"
    assert not mundo.consulta("SELECT 1 FROM auditoria WHERE accion = 'EDICION' AND datos_nuevos LIKE '%fecha_inicio%'")


def test_editar_con_la_fecha_de_inicio_vacia_la_quita(admin, mundo, tarea):  # noqa: F811
    assert _editar(admin, tarea, fecha_inicio=None).status_code == 200
    assert mundo.consulta("SELECT fecha_inicio FROM tarea WHERE id_tarea = %s", (tarea,))[0]["fecha_inicio"] is None


@pytest.mark.parametrize("extra", [{"fecha_inicio": "2027-01-05"}, {"fecha_vencimiento": "2026-11-20"}])
def test_editar_rechaza_un_inicio_posterior_al_vencimiento_aunque_solo_cambie_una(admin, mundo, tarea, extra):  # noqa: F811
    respuesta = _editar(admin, tarea, **extra)

    assert respuesta.status_code == 400
    assert mundo.consulta("SELECT fecha_inicio FROM tarea WHERE id_tarea = %s", (tarea,))[0]["fecha_inicio"].date().isoformat() == "2026-12-01"


def test_una_tarea_anterior_sin_fecha_de_inicio_se_edita_sin_problema(admin, mundo):  # noqa: F811
    historica = mundo.consulta("SELECT id_tarea FROM tarea ORDER BY id_tarea LIMIT 1")[0]["id_tarea"]
    assert mundo.consulta("SELECT fecha_inicio FROM tarea WHERE id_tarea = %s", (historica,))[0]["fecha_inicio"] is None

    assert _editar(admin, historica, titulo="Revisada").status_code == 200
    assert admin.get(f"/api/tareas/{historica}").get_json()["fecha_inicio"] is None
