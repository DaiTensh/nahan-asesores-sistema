# -*- coding: utf-8 -*-
"""Brechas de verificación de RF05, RF31, RF32 y RF41 (auditoría A0), contra MySQL real.

A0 las dejó «sin verificación suficiente»: cada una tenía una sola prueba indirecta. Aquí se prueba el
contenido: búsqueda por razón social y RUT (RF05), reportes por cliente y por responsable con su
resumen por estado (RF31, RF32) y el resumen de clientes del dashboard (RF41).
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
PERIODO = "fecha_inicio=2026-01-01&fecha_fin=2030-12-31"


@pytest.fixture
def admin(client, iniciar_sesion, mundo):  # noqa: F811
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    return client


@pytest.fixture
def ejecutar(servidor):  # noqa: F811
    def _ejecutar(sql, params=()):
        cn = servidor.conectar(base=BASE_APP)
        cur = cn.cursor()
        cur.execute(sql, params)
        cn.commit()
        ultimo = cur.lastrowid
        cn.close()
        return ultimo
    return _ejecutar


def _tarea(ejecutar, estado, cliente, responsable):
    return ejecutar("INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado) VALUES (%s, 1, %s, 1, %s, %s)",
                    (cliente, responsable, f"{estado} de {cliente}/{responsable}", estado))


# ---------------------------------------------------------------------------
# RF05: búsqueda específica de clientes
# ---------------------------------------------------------------------------

def _buscar(client, texto, extra=""):
    respuesta = client.get(f"/api/clientes/filtrar?buscar={texto}{extra}")
    assert respuesta.status_code == 200
    return [c["id_cliente"] for c in respuesta.get_json()]


def test_se_busca_un_cliente_por_razon_social_sin_distinguir_mayusculas_ni_acentos(admin):
    assert _buscar(admin, "CLIENTE%20dos") == [2]
    assert _buscar(admin, "nandu") == [1], "el collation utf8mb4_unicode_ci ignora tildes y mayúsculas"


def test_se_busca_un_cliente_por_rut_parcial(admin):
    assert _buscar(admin, "22.222") == [2]
    assert _buscar(admin, "11.111.111-1") == [1]


def test_una_busqueda_sin_coincidencias_devuelve_una_lista_vacia(admin):
    assert _buscar(admin, "zzzz-no-existe") == []


def test_la_busqueda_se_combina_con_el_area(admin, ejecutar):
    ejecutar("INSERT INTO cliente_area (id_cliente, id_area, fecha_asignacion) VALUES (2, 1, NOW())")

    assert _buscar(admin, "Cliente", "&id_area=1") == [2]
    assert _buscar(admin, "Cliente", "&id_area=2") == []


def test_la_busqueda_exige_sesion_y_la_hace_cualquier_rol_operativo(client, iniciar_sesion, mundo):  # noqa: F811
    assert client.get("/api/clientes/filtrar?buscar=Cliente").status_code == 401
    iniciar_sesion(usuario_id=ID_JURIDICA, rol_id=2, area_id=1)
    assert 2 in _buscar(client, "Cliente")


# ---------------------------------------------------------------------------
# RF41: resumen de clientes del dashboard
# ---------------------------------------------------------------------------

def test_el_resumen_de_clientes_cuenta_activos_e_inactivos(admin):
    resumen = admin.get("/api/clientes/resumen").get_json()
    assert (resumen["total_clientes"], resumen["clientes_activos"], resumen["clientes_inactivos"]) == (2, 2, 0)

    assert admin.patch("/api/clientes/1/deshabilitar").status_code == 200
    resumen = admin.get("/api/clientes/resumen").get_json()
    assert (resumen["total_clientes"], resumen["clientes_activos"], resumen["clientes_inactivos"]) == (2, 1, 1)


def test_el_resumen_de_clientes_lista_a_lo_mas_cinco_y_exige_sesion(admin, ejecutar, client):
    for i in range(3, 9):
        ejecutar("INSERT INTO cliente (rut, razon_social) VALUES (%s, %s)", (f"{i}0.000.000-0", f"Cliente {i}"))

    resumen = admin.get("/api/clientes/resumen").get_json()

    assert resumen["total_clientes"] == 8 and len(resumen["ultimos_clientes"]) == 5
    client.post("/api/logout")  # sin sesión
    assert client.get("/api/clientes/resumen").status_code in (401, 403)


# ---------------------------------------------------------------------------
# RF31 y RF32: reportes de tareas por cliente y por responsable
# ---------------------------------------------------------------------------

@pytest.fixture
def tareas(ejecutar):
    # Cliente 1 / usuaria 2: una por estado activo y una finalizada. Cliente 2 / admin: una pendiente.
    for estado in ("PENDIENTE", "EN_PROCESO", "PAUSADA", "COMPLETADA"):
        _tarea(ejecutar, estado, 1, ID_JURIDICA)
    _tarea(ejecutar, "PENDIENTE", 2, ID_ADMIN)


def test_el_reporte_por_cliente_trae_solo_sus_tareas_y_el_resumen_por_estado(admin, tareas):
    respuesta = admin.get(f"/api/reportes/tareas-por-cliente?id_cliente=1&{PERIODO}")
    datos = respuesta.get_json()

    assert respuesta.status_code == 200 and datos["cliente"]["id_cliente"] == 1
    titulos = {t["titulo"] for t in datos["tareas"]}
    assert titulos >= {"PENDIENTE de 1/2", "EN_PROCESO de 1/2", "PAUSADA de 1/2", "COMPLETADA de 1/2"}
    assert not any("/" in t and t.split(" de ")[1].startswith("2/") for t in titulos), "no mezcla las del cliente 2"
    resumen = datos["resumen_por_estado"]
    assert resumen["PAUSADA"] == 1 and resumen["COMPLETADA"] == 1 and resumen["EN_PROCESO"] == 1


def test_el_reporte_por_responsable_trae_solo_las_tareas_de_esa_persona(admin, tareas):
    respuesta = admin.get(f"/api/reportes/tareas-por-responsable?id_responsable={ID_JURIDICA}&{PERIODO}")
    datos = respuesta.get_json()

    assert respuesta.status_code == 200 and datos["responsable"]["id_usuario"] == ID_JURIDICA
    assert {t["titulo"].split(" de ")[1] for t in datos["tareas"]} == {"1/2"}
    assert sum(datos["resumen_por_estado"].values()) == len(datos["tareas"]) >= 4


def test_los_reportes_son_solo_del_administrador_y_validan_la_entidad(client, iniciar_sesion, admin, tareas):  # noqa: F811
    assert admin.get(f"/api/reportes/tareas-por-cliente?id_cliente=9999&{PERIODO}").status_code in (400, 404)
    assert admin.get(f"/api/reportes/tareas-por-responsable?id_responsable=9999&{PERIODO}").status_code in (400, 404)

    iniciar_sesion(usuario_id=ID_JURIDICA, rol_id=2, area_id=1)
    assert client.get(f"/api/reportes/tareas-por-cliente?id_cliente=1&{PERIODO}").status_code == 403
    assert client.get(f"/api/reportes/tareas-por-responsable?id_responsable=2&{PERIODO}").status_code == 403
