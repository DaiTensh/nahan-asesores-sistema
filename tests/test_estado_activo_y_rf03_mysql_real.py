# -*- coding: utf-8 -*-
"""Estado «activo» de una tarea (RF39, RF61) y reglas de cliente de RF03/RF10, contra MySQL real.

Una tarea está activa en PENDIENTE, EN_PROCESO, PAUSADA y EN_REVISION (backend/utils/estados_tarea.py).
Antes, la carga vigente de RF39 y el contador de la ficha (RF61) solo contaban los dos primeros.

RF03 (Documento 0): la eliminación definitiva solo procede sin tareas activas ni documentos
vigentes; con vínculos activos solo se ofrece deshabilitar. La pantalla ya lo hacía; estas pruebas
fijan que el servidor también lo exige ante una llamada directa a la API.

RF10, criterio 4: «No se pueden crear tareas para clientes inactivos».
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
ESTADOS_ACTIVOS = ["PENDIENTE", "EN_PROCESO", "PAUSADA", "EN_REVISION"]
ESTADOS_FINALES = ["COMPLETADA", "CANCELADA"]


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


def _tarea(ejecutar, estado, cliente, responsable=ID_JURIDICA):
    return ejecutar(
        "INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado) "
        "VALUES (%s, 1, %s, 1, %s, %s)", (cliente, responsable, f"Tarea {estado}", estado))


def _cliente(ejecutar, rut, nombre="Cliente de prueba", estado="ACTIVO"):
    return ejecutar(
        "INSERT INTO cliente (rut, razon_social, email, telefono, direccion, estado) "
        "VALUES (%s, %s, 'c@ejemplo.invalid', '+56 9 0000 0009', 'Calle Falsa 1', %s)", (rut, nombre, estado))


# ---------------------------------------------------------------------------
# RF39 / RF35: carga vigente
# ---------------------------------------------------------------------------

def test_la_carga_vigente_de_rf39_cuenta_los_cuatro_estados_activos_y_no_los_finales(admin, ejecutar):
    cliente = _cliente(ejecutar, "33.333.333-3")
    for estado in ESTADOS_ACTIVOS + ESTADOS_FINALES:
        _tarea(ejecutar, estado, cliente)

    respuesta = admin.get("/api/reportes/productividad?fecha_inicio=2026-01-01&fecha_fin=2026-12-31")
    fila = next(f for f in respuesta.get_json()["usuarios"] if f["id_usuario"] == ID_JURIDICA)

    assert respuesta.status_code == 200
    assert fila["carga_vigente"] == 4


@pytest.mark.parametrize("estado", ESTADOS_ACTIVOS)
def test_cada_estado_activo_suma_uno_a_la_carga_vigente(admin, ejecutar, estado):
    cliente = _cliente(ejecutar, "33.333.333-3")
    _tarea(ejecutar, estado, cliente)

    respuesta = admin.get("/api/reportes/productividad?fecha_inicio=2026-01-01&fecha_fin=2026-12-31")
    fila = next(f for f in respuesta.get_json()["usuarios"] if f["id_usuario"] == ID_JURIDICA)

    assert fila["carga_vigente"] == 1


# ---------------------------------------------------------------------------
# RF61: tareas activas de la ficha
# ---------------------------------------------------------------------------

def test_la_ficha_cuenta_como_activas_las_tareas_de_los_cuatro_estados(admin, ejecutar):
    cliente = _cliente(ejecutar, "44.444.444-4")
    for estado in ESTADOS_ACTIVOS + ESTADOS_FINALES:
        _tarea(ejecutar, estado, cliente)

    respuesta = admin.get(f"/api/clientes/{cliente}/ficha")

    assert respuesta.status_code == 200
    assert respuesta.get_json()["tareas_activas"] == 4


def test_la_ficha_y_los_vinculos_coinciden_en_las_tareas_activas(admin, ejecutar):
    cliente = _cliente(ejecutar, "44.444.444-4")
    for estado in ESTADOS_ACTIVOS + ESTADOS_FINALES:
        _tarea(ejecutar, estado, cliente)

    ficha = admin.get(f"/api/clientes/{cliente}/ficha").get_json()["tareas_activas"]
    vinculos = admin.get(f"/api/clientes/{cliente}/verificar-vinculos").get_json()["tareas_activas"]

    assert ficha == vinculos == 4


# ---------------------------------------------------------------------------
# RF03: el servidor exige lo que la pantalla ya impide
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("estado", ESTADOS_ACTIVOS)
def test_no_se_elimina_definitivamente_un_cliente_con_tareas_activas(admin, mundo, ejecutar, estado):  # noqa: F811
    cliente = _cliente(ejecutar, "55.555.555-5")
    _tarea(ejecutar, estado, cliente)

    respuesta = admin.delete(f"/api/clientes/{cliente}/eliminar-definitivo")

    assert respuesta.status_code == 409
    assert respuesta.get_json()["tareas_activas"] == 1
    assert mundo.consulta("SELECT 1 FROM cliente WHERE id_cliente = %s", (cliente,)), "el cliente sigue existiendo"
    assert not mundo.consulta("SELECT 1 FROM auditoria WHERE accion = 'ELIMINACION_DEFINITIVA'")


def test_no_se_elimina_definitivamente_un_cliente_con_documentos_vigentes(admin, mundo):  # noqa: F811
    # El cliente 1 del mundo ficticio tiene una tarea y un documento vigente.
    respuesta = admin.delete("/api/clientes/1/eliminar-definitivo")

    assert respuesta.status_code == 409
    assert mundo.consulta("SELECT 1 FROM cliente WHERE id_cliente = 1")


def test_un_cliente_solo_con_tareas_finalizadas_responde_409_y_no_500(admin, mundo, ejecutar):  # noqa: F811
    cliente = _cliente(ejecutar, "66.666.666-6")
    _tarea(ejecutar, "COMPLETADA", cliente)

    respuesta = admin.delete(f"/api/clientes/{cliente}/eliminar-definitivo")

    assert respuesta.status_code == 409, "el historial se conserva; antes era un 500 genérico"
    assert "historial" in respuesta.get_json()["error"]
    assert mundo.consulta("SELECT 1 FROM cliente WHERE id_cliente = %s", (cliente,))
    assert not mundo.consulta("SELECT 1 FROM auditoria WHERE accion = 'ELIMINACION_DEFINITIVA'")


def test_un_cliente_sin_vinculos_si_se_elimina_definitivamente(admin, mundo, ejecutar):  # noqa: F811
    cliente = _cliente(ejecutar, "77.777.777-7")

    respuesta = admin.delete(f"/api/clientes/{cliente}/eliminar-definitivo")

    assert respuesta.status_code == 200
    assert not mundo.consulta("SELECT 1 FROM cliente WHERE id_cliente = %s", (cliente,))
    assert mundo.consulta("SELECT 1 FROM auditoria WHERE accion = 'ELIMINACION_DEFINITIVA'")


def test_con_vinculos_activos_si_se_puede_deshabilitar_como_ofrece_la_pantalla(admin, mundo):  # noqa: F811
    respuesta = admin.patch("/api/clientes/1/deshabilitar")

    assert respuesta.status_code == 200
    assert mundo.consulta("SELECT estado FROM cliente WHERE id_cliente = 1")[0]["estado"] == "INACTIVO"


# ---------------------------------------------------------------------------
# RF10 (criterio 4) y RF03: sin tareas nuevas para clientes inactivos
# ---------------------------------------------------------------------------

def _crear_tarea(client, id_cliente):
    return client.post("/api/tareas", json={
        "id_cliente": id_cliente, "areas": [1], "id_responsable": ID_ADMIN,
        "titulo": "Tarea nueva", "prioridad": "MEDIA"})


def test_no_se_crean_tareas_para_un_cliente_inactivo(admin, mundo, ejecutar):  # noqa: F811
    cliente = _cliente(ejecutar, "88.888.888-8", estado="INACTIVO")
    antes = len(mundo.consulta("SELECT 1 FROM tarea"))

    respuesta = _crear_tarea(admin, cliente)

    assert respuesta.status_code == 409
    assert "inactivo" in respuesta.get_json()["error"]
    assert len(mundo.consulta("SELECT 1 FROM tarea")) == antes


def test_un_cliente_deshabilitado_por_rf03_deja_de_aceptar_tareas(admin, mundo):  # noqa: F811
    assert admin.patch("/api/clientes/1/deshabilitar").status_code == 200

    assert _crear_tarea(admin, 1).status_code == 409


def test_un_cliente_reactivado_vuelve_a_aceptar_tareas(admin, mundo):  # noqa: F811
    assert admin.patch("/api/clientes/1/deshabilitar").status_code == 200
    assert admin.post("/api/clientes/1/cambiar-estado", json={"nuevo_estado": "ACTIVO"}).status_code == 200

    assert _crear_tarea(admin, 1).status_code == 201


def test_un_cliente_inexistente_sigue_respondiendo_404(admin, mundo):  # noqa: F811
    assert _crear_tarea(admin, 9999).status_code == 404


# ---------------------------------------------------------------------------
# RF47: abrir la «Ficha del Cliente» alimenta «Mis clientes recientes»
# ---------------------------------------------------------------------------

def _recientes(client):
    return [c["id_cliente"] for c in client.get("/api/clientes/recientes").get_json()["clientes_recientes"]]


def test_abrir_la_ficha_registra_al_cliente_como_reciente(admin, mundo):  # noqa: F811
    assert admin.get("/api/clientes/2/ficha").status_code == 200
    assert admin.get("/api/clientes/1/ficha").status_code == 200

    assert _recientes(admin) == [1, 2], "el más reciente primero"


def test_una_ficha_inactiva_no_se_registra_como_reciente(admin, mundo, ejecutar):  # noqa: F811
    inactivo = _cliente(ejecutar, "99.999.999-9", estado="INACTIVO")

    assert admin.get(f"/api/clientes/{inactivo}/ficha").status_code == 200

    assert inactivo not in _recientes(admin)


def test_el_historial_de_recientes_es_de_cada_persona(client, iniciar_sesion, mundo):  # noqa: F811
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    assert client.get("/api/clientes/2/ficha").status_code == 200
    iniciar_sesion(usuario_id=ID_JURIDICA, rol_id=2, area_id=1)

    assert _recientes(client) == []
