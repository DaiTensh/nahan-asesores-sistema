# -*- coding: utf-8 -*-
"""RF17 — Actualizando el Estado de Tareas: pendiente, en proceso, pausada o finalizada.

El texto oficial nombra el estado «pausada», que el sistema no tenía. Se agrega
PAUSADA (migración 011) como un estado **abierto** más: se mueve libremente desde y
hacia pendiente y en proceso, puede enviarse a revisión (RF76) y sigue contando como
trabajo por hacer en listados, resúmenes, vencimientos y vínculos del cliente. Solo el
administrador puede aplicar estados finales, igual que antes. Se prueba contra un
MySQL real y desechable porque el estado es una columna ENUM.
"""
import os

import pytest

from tests.mysql_desechable import BASE_APP, herramientas_disponibles
from tests.test_rf74_mysql_real import mundo, servidor  # noqa: F401  (fixtures compartidas)

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)

ID_ADMIN, ID_AREA_JURIDICA = 1, 2


@pytest.fixture
def nueva_tarea(mundo, servidor):  # noqa: F811
    """Crea una tarea del usuario de área jurídica (id 2) y devuelve su id."""
    def crear(estado="PENDIENTE", cliente=1, vencimiento="2026-12-31", responsable=ID_AREA_JURIDICA, titulo="Tarea de prueba"):
        cn = servidor.conectar(base=BASE_APP)
        cur = cn.cursor()
        cur.execute(
            "INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado, fecha_vencimiento) "
            "VALUES (%s, 1, %s, 1, %s, %s, %s)", (cliente, responsable, titulo, estado, vencimiento))
        cn.commit()
        id_tarea = cur.lastrowid
        cn.close()
        return id_tarea
    return crear


def _estado(mundo, id_tarea):  # noqa: F811
    return mundo.consulta("SELECT estado FROM tarea WHERE id_tarea = %s", (id_tarea,))[0]["estado"]


def _cambiar(client, id_tarea, estado):
    return client.put(f"/api/tareas/{id_tarea}/estado", json={"estado": estado})


# ---------------------------------------------------------------------------
# Transiciones
# ---------------------------------------------------------------------------

def test_el_responsable_pausa_y_reanuda_su_tarea_pasando_por_los_estados_abiertos(client, iniciar_sesion, mundo, nueva_tarea):  # noqa: F811
    iniciar_sesion(usuario_id=ID_AREA_JURIDICA, rol_id=2, area_id=1)
    id_tarea = nueva_tarea("PENDIENTE")

    secuencia = ["EN_PROCESO", "PAUSADA", "EN_PROCESO", "PAUSADA", "PENDIENTE"]
    for estado in secuencia:
        assert _cambiar(client, id_tarea, estado).status_code == 200, estado
        assert _estado(mundo, id_tarea) == estado

    eventos = mundo.consulta("SELECT datos_anteriores, datos_nuevos FROM auditoria WHERE accion = 'CAMBIO_ESTADO_TAREA' ORDER BY id_auditoria")
    assert [(e["datos_anteriores"].split("estado=")[1], e["datos_nuevos"].split("estado=")[1]) for e in eventos] == [
        ("PENDIENTE", "EN_PROCESO"), ("EN_PROCESO", "PAUSADA"), ("PAUSADA", "EN_PROCESO"), ("EN_PROCESO", "PAUSADA"), ("PAUSADA", "PENDIENTE")]


def test_pausar_desde_pendiente_y_repetir_el_mismo_estado_es_inofensivo(client, iniciar_sesion, mundo, nueva_tarea):  # noqa: F811
    iniciar_sesion(usuario_id=ID_AREA_JURIDICA, rol_id=2, area_id=1)
    id_tarea = nueva_tarea("PENDIENTE")

    assert _cambiar(client, id_tarea, "PAUSADA").status_code == 200
    assert _cambiar(client, id_tarea, "PAUSADA").status_code == 200
    assert _estado(mundo, id_tarea) == "PAUSADA"
    assert len(mundo.consulta("SELECT 1 FROM auditoria WHERE accion = 'CAMBIO_ESTADO_TAREA'")) == 1, "repetir no deja otro evento"


def test_el_administrador_que_pausa_avisa_al_responsable(client, iniciar_sesion, mundo, nueva_tarea):  # noqa: F811
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    id_tarea = nueva_tarea("EN_PROCESO")

    assert _cambiar(client, id_tarea, "PAUSADA").status_code == 200

    aviso = mundo.consulta("SELECT mensaje, id_usuario FROM notificacion WHERE tipo = 'CAMBIO_ESTADO_TAREA'")[0]
    assert aviso["id_usuario"] == ID_AREA_JURIDICA and "de «En proceso» a «Pausada»" in aviso["mensaje"]


def test_nadie_pausa_la_tarea_de_otra_persona(client, iniciar_sesion, mundo, nueva_tarea):  # noqa: F811
    id_tarea = nueva_tarea("EN_PROCESO", responsable=ID_ADMIN)
    iniciar_sesion(usuario_id=ID_AREA_JURIDICA, rol_id=2, area_id=1)

    assert _cambiar(client, id_tarea, "PAUSADA").status_code == 403
    assert _estado(mundo, id_tarea) == "EN_PROCESO"


@pytest.mark.parametrize("final", ["COMPLETADA", "CANCELADA"])
def test_una_tarea_pausada_solo_la_finaliza_el_administrador(client, iniciar_sesion, mundo, nueva_tarea, final):  # noqa: F811
    id_tarea = nueva_tarea("PAUSADA")
    iniciar_sesion(usuario_id=ID_AREA_JURIDICA, rol_id=2, area_id=1)
    assert _cambiar(client, id_tarea, final).status_code == 403

    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    assert _cambiar(client, id_tarea, final).status_code == 200
    assert _estado(mundo, id_tarea) == final


@pytest.mark.parametrize("final", ["COMPLETADA", "CANCELADA"])
def test_una_tarea_finalizada_no_vuelve_a_pausada(client, iniciar_sesion, mundo, nueva_tarea, final):  # noqa: F811
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    id_tarea = nueva_tarea(final)

    assert _cambiar(client, id_tarea, "PAUSADA").status_code == 409
    assert _estado(mundo, id_tarea) == final


def test_un_estado_que_no_existe_sigue_rechazandose(client, iniciar_sesion, nueva_tarea):
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    assert _cambiar(client, nueva_tarea(), "SUSPENDIDA").status_code == 400


def test_la_tarea_pausada_puede_enviarse_a_revision_y_si_se_rechaza_vuelve_a_pausada(client, iniciar_sesion, mundo, nueva_tarea):  # noqa: F811
    id_tarea = nueva_tarea("PAUSADA")
    iniciar_sesion(usuario_id=ID_AREA_JURIDICA, rol_id=2, area_id=1)
    assert _cambiar(client, id_tarea, "EN_REVISION").status_code == 200

    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    respuesta = client.put(f"/api/tareas/{id_tarea}/revision", json={"accion": "rechazar", "observaciones": "Falta el anexo"})

    assert respuesta.status_code == 200
    assert _estado(mundo, id_tarea) == "PAUSADA", "RF76: el rechazo devuelve la tarea al estado anterior"


def test_una_tarea_pausada_se_puede_editar_y_cambiar_de_prioridad(client, iniciar_sesion, mundo, nueva_tarea):  # noqa: F811
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    id_tarea = nueva_tarea("PAUSADA")

    editar = client.put(f"/api/tareas/{id_tarea}", json={"titulo": "Retomar en enero", "id_responsable": ID_AREA_JURIDICA, "prioridad": "ALTA",
                                                         "fecha_vencimiento": "2026-12-31"})
    prioridad = client.put(f"/api/tareas/{id_tarea}/prioridad", json={"prioridad": "URGENTE"})

    assert (editar.status_code, prioridad.status_code) == (200, 200)
    assert _estado(mundo, id_tarea) == "PAUSADA"


# ---------------------------------------------------------------------------
# Una tarea pausada sigue siendo trabajo abierto
# ---------------------------------------------------------------------------

def test_los_listados_incluyen_la_tarea_pausada_y_se_puede_filtrar_por_ese_estado(client, iniciar_sesion, nueva_tarea):
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    pausada = nueva_tarea("PAUSADA", titulo="En pausa")
    abierta = nueva_tarea("PENDIENTE", titulo="Abierta")
    cerrada = nueva_tarea("COMPLETADA", titulo="Cerrada")

    por_defecto = {t["id_tarea"]: t["estado"] for t in client.get("/api/tareas/pendientes").get_json()}
    solo_pausadas = client.get("/api/tareas/pendientes", query_string={"estado": "PAUSADA"}).get_json()

    assert por_defecto[pausada] == "PAUSADA" and abierta in por_defecto and cerrada not in por_defecto
    assert [t["id_tarea"] for t in solo_pausadas] == [pausada]


def test_los_resumenes_cuentan_las_pausadas(client, iniciar_sesion, mundo, nueva_tarea):  # noqa: F811
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    for estado in ("PAUSADA", "PAUSADA", "EN_PROCESO", "COMPLETADA"):
        nueva_tarea(estado)
    base = mundo.consulta("SELECT estado, COUNT(*) AS n FROM tarea GROUP BY estado")
    esperadas = {f["estado"]: f["n"] for f in base}

    resumen = client.get("/api/tareas/resumen").get_json()   # RF50

    assert resumen["PAUSADA"] == esperadas["PAUSADA"] >= 2
    assert sum(resumen.values()) == sum(esperadas.values()), "los totales por estado cuadran con la base"
    carga = client.get("/api/reportes/carga-por-usuario").get_json()   # RF44
    fila = next(u for u in carga["usuarios"] if u["id_usuario"] == ID_AREA_JURIDICA)
    assert fila["por_estado"]["PAUSADA"] == 2 and fila["total_tareas"] == sum(fila["por_estado"].values())


def test_una_tarea_pausada_vencida_aparece_en_vencidas_y_por_vencer(client, iniciar_sesion, nueva_tarea):
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    vencida = nueva_tarea("PAUSADA", vencimiento="2020-01-01", titulo="Vencida en pausa")

    assert vencida in [t["id_tarea"] for t in client.get("/api/tareas/vencidas").get_json()]


def test_un_cliente_con_una_tarea_pausada_tiene_vinculos_activos(client, iniciar_sesion, nueva_tarea):
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    nueva_tarea("PAUSADA", cliente=2)

    datos = client.get("/api/clientes/2/verificar-vinculos").get_json()

    assert datos["tiene_vinculos"] is True and datos["tareas_activas"] == 1, "no debe ofrecerse eliminar al cliente"


def test_se_puede_iniciar_el_temporizador_en_una_tarea_pausada(client, iniciar_sesion, mundo, nueva_tarea):  # noqa: F811
    """Decisión de diseño: PAUSADA no agrega ninguna restricción nueva al registro de horas."""
    iniciar_sesion(usuario_id=ID_AREA_JURIDICA, rol_id=2, area_id=1)
    id_tarea = nueva_tarea("PAUSADA")

    assert client.post("/api/control-horas/iniciar", json={"id_tarea": id_tarea}).status_code in (200, 201)


def test_el_reporte_por_cliente_incluye_las_pausadas_en_su_resumen(client, iniciar_sesion, nueva_tarea):
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)
    nueva_tarea("PAUSADA")

    datos = client.get("/api/reportes/tareas-por-cliente",
                       query_string={"id_cliente": 1, "fecha_inicio": "2020-01-01", "fecha_fin": "2030-12-31"}).get_json()

    assert datos["resumen_por_estado"]["PAUSADA"] == 1


# ---------------------------------------------------------------------------
# Esquema y compatibilidad
# ---------------------------------------------------------------------------

def test_el_esquema_acepta_pausada_sin_cambiar_los_valores_existentes(mundo):  # noqa: F811
    columna = mundo.consulta(
        "SELECT column_type AS tipo, column_default AS por_defecto FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = 'tarea' AND column_name = 'estado'")[0]
    tipo = columna["tipo"] if isinstance(columna["tipo"], str) else columna["tipo"].decode()

    assert tipo == "enum('PENDIENTE','EN_PROCESO','EN_REVISION','COMPLETADA','CANCELADA','PAUSADA')", "PAUSADA va al final: no reordena los valores"
    assert columna["por_defecto"] == "PENDIENTE"


# ---------------------------------------------------------------------------
# Pantallas
# ---------------------------------------------------------------------------

def _leer(*partes):
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "frontend", *partes), encoding="utf-8") as archivo:
        return archivo.read()


def test_las_pantallas_ofrecen_y_nombran_el_estado_pausada():
    assert '["PAUSADA", "Pausada"]' in _leer("tareas", "tareas.js")
    assert 'PAUSADA: "Pausada"' in _leer("tareas", "detalle_tarea.js")
    assert '<option value="PAUSADA">Pausada</option>' in _leer("tareas", "tareas.html")
    assert 'id="totalPausadas"' in _leer("tareas", "tareas.html") and 'id="resumenPausada"' in _leer("dashboard", "dashboard.html")
    assert "por_estado.PAUSADA" in _leer("dashboard", "dashboard.js") and "resumen.PAUSADA" in _leer("dashboard", "dashboard.js")
    assert "repeat(5, minmax(0, 1fr))" in _leer("tareas", "tareas.css"), "cinco tarjetas de resumen caben en una fila"
    assert ".badge.estado-pausada" in _leer("tareas", "tareas.css") and "estado-pausada" in _leer("assets", "css", "badges.css")
