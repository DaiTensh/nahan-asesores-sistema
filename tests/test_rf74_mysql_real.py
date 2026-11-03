"""RF74 contra un MySQL real y desechable: precedencia, historial y efecto sobre RF71-RF75."""
import os
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.routes import control_horas_routes
from tests.mysql_desechable import (
    BASE_APP, CLAVE_APP, USUARIO_APP, MySQLDesechable, herramientas_disponibles, sembrar_datos_ficticios,
)

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)


@pytest.fixture(scope="module")
def servidor():
    servidor = MySQLDesechable().iniciar()
    yield servidor
    servidor.detener()


@pytest.fixture
def mundo(servidor, monkeypatch):
    root = servidor.conectar()
    cur = root.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {BASE_APP}")
    cur.execute(f"CREATE DATABASE {BASE_APP} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    root.close()
    servidor.cargar_esquema()
    cn = servidor.conectar(base=BASE_APP)
    sembrar_datos_ficticios(cn)
    cn.close()
    for clave, valor in {"DB_HOST": "127.0.0.1", "DB_PORT": str(servidor.puerto), "DB_USER": USUARIO_APP,
                         "DB_PASSWORD": CLAVE_APP, "DB_NAME": BASE_APP}.items():
        monkeypatch.setenv(clave, valor)

    class Mundo(SimpleNamespace):
        def consulta(self, sql, params=()):
            cn = servidor.conectar(base=BASE_APP)
            cur = cn.cursor(dictionary=True)
            cur.execute(sql, params)
            filas = cur.fetchall()
            cn.close()
            return filas

        def vigente(self, id_area):
            cn = servidor.conectar(base=BASE_APP)
            cur = cn.cursor(dictionary=True)
            try:
                return control_horas_routes._obtener_tarifa_vigente(cur, id_area)
            finally:
                cn.close()
    return Mundo()


def test_el_flujo_completo_de_tarifas_con_precedencia_historial_y_auditoria(client, iniciar_sesion, mundo):
    iniciar_sesion(usuario_id=1, rol_id=1)

    inicial = client.get("/api/tarifas").get_json()
    assert inicial["general"] == {"valor_hora": 30000.0, "moneda": "CLP"}
    assert [a["valor_hora"] for a in inicial["areas"]] == [None, None, None]
    assert mundo.vigente(1) == Decimal("30000")

    assert client.put("/api/tarifas/general", json={"valor_hora": "45000.50"}).status_code == 200
    assert mundo.vigente(1) == Decimal("45000.50") and mundo.vigente(2) == Decimal("45000.50")

    assert client.put("/api/tarifas/areas/1", json={"valor_hora": 38000}).status_code == 200
    assert mundo.vigente(1) == Decimal("38000.00"), "la tarifa del área tiene precedencia"
    assert mundo.vigente(2) == Decimal("45000.50"), "las demás áreas siguen con la general"

    assert client.put("/api/tarifas/areas/1", json={"valor_hora": 41000}).status_code == 200
    assert mundo.vigente(1) == Decimal("41000.00")
    historial = mundo.consulta("SELECT valor_hora, estado, fecha_fin IS NOT NULL AS cerrada FROM tarifa_hora WHERE id_area = 1 ORDER BY id_tarifa")
    assert [(str(h["valor_hora"]), h["estado"], bool(h["cerrada"])) for h in historial] == [("38000.00", "INACTIVA", True), ("41000.00", "ACTIVA", False)]

    despues = client.get("/api/tarifas").get_json()["areas"][0]
    assert (despues["valor_hora"], despues["tarifa_aplicada"]) == (41000.0, 41000.0)

    assert client.delete("/api/tarifas/areas/1").status_code == 200
    assert mundo.vigente(1) == Decimal("45000.50"), "sin tarifa propia vuelve a la general"
    assert client.delete("/api/tarifas/areas/1").status_code == 404
    assert len(mundo.consulta("SELECT id_tarifa FROM tarifa_hora WHERE id_area = 1")) == 2, "el historial no se borra"

    acciones = [(e["accion"], e["tabla_afectada"]) for e in mundo.consulta("SELECT * FROM auditoria ORDER BY id_auditoria")]
    assert acciones == [("CONFIGURAR_TARIFA_GENERAL", "parametros_sistema"), ("TARIFA_AREA_DEFINIDA", "tarifa_hora"),
                        ("TARIFA_AREA_DEFINIDA", "tarifa_hora"), ("TARIFA_AREA_ELIMINADA", "tarifa_hora")]
    ultima = mundo.consulta("SELECT * FROM auditoria WHERE accion = 'TARIFA_AREA_DEFINIDA' ORDER BY id_auditoria DESC LIMIT 1")[0]
    assert (ultima["datos_anteriores"], ultima["datos_nuevos"]) == ("id_area=1, valor_hora=38000.00", "id_area=1, valor_hora=41000.00")

    eventos = client.get("/api/historial", query_string={"modulo": "Configuración"}).get_json()["eventos"]
    assert {e["accion"] for e in eventos} >= {"CONFIGURAR_TARIFA_GENERAL", "TARIFA_AREA_DEFINIDA", "TARIFA_AREA_ELIMINADA"}


def test_un_registro_de_tiempo_cerrado_conserva_la_tarifa_con_la_que_se_calculo(client, iniciar_sesion, mundo):
    iniciar_sesion(usuario_id=1, rol_id=1)
    assert client.put("/api/tarifas/areas/1", json={"valor_hora": 36000}).status_code == 200

    assert client.post("/api/control-horas/iniciar", json={"id_tarea": 1}).status_code in (200, 201)
    assert client.post("/api/control-horas/detener").status_code == 200
    primero = mundo.consulta("SELECT tarifa_hora FROM registro_tiempo ORDER BY id_registro DESC LIMIT 1")[0]["tarifa_hora"]
    assert primero == Decimal("36000.00")

    assert client.put("/api/tarifas/areas/1", json={"valor_hora": 52000}).status_code == 200
    assert mundo.consulta("SELECT tarifa_hora FROM registro_tiempo ORDER BY id_registro LIMIT 1")[0]["tarifa_hora"] == Decimal("36000.00")

    assert client.post("/api/control-horas/iniciar", json={"id_tarea": 1}).status_code in (200, 201)
    assert client.post("/api/control-horas/detener").status_code == 200
    tarifas = [f["tarifa_hora"] for f in mundo.consulta("SELECT tarifa_hora FROM registro_tiempo ORDER BY id_registro")]
    assert tarifas == [Decimal("36000.00"), Decimal("52000.00")]


def test_un_usuario_operativo_no_cambia_ninguna_tarifa(client, iniciar_sesion, mundo):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)
    assert client.put("/api/tarifas/general", json={"valor_hora": 1}).status_code == 403
    assert client.put("/api/tarifas/areas/1", json={"valor_hora": 1}).status_code == 403
    assert client.delete("/api/tarifas/areas/1").status_code == 403
    assert mundo.vigente(1) == Decimal("30000")
    assert mundo.consulta("SELECT COUNT(*) AS n FROM auditoria")[0]["n"] == 0


def test_el_monto_de_un_registro_es_la_duracion_por_la_tarifa_vigente_al_iniciar(client, iniciar_sesion, mundo, servidor):
    """90 minutos a la tarifa del área: 90/60 × 36 000 = 54 000; un cambio posterior de tarifa no lo altera."""
    iniciar_sesion(usuario_id=1, rol_id=1)
    assert client.put("/api/tarifas/areas/1", json={"valor_hora": 36000}).status_code == 200
    assert client.post("/api/control-horas/iniciar", json={"id_tarea": 1}).status_code in (200, 201)

    cn = servidor.conectar(base=BASE_APP)
    cn.cursor().execute("UPDATE registro_tiempo SET fecha = DATE(NOW() - INTERVAL 90 MINUTE), "
                        "hora_inicio = TIME(NOW() - INTERVAL 90 MINUTE) WHERE hora_fin IS NULL")
    cn.commit()
    cn.close()
    assert client.post("/api/control-horas/detener").status_code == 200

    fila = mundo.consulta("SELECT duracion_minutos, tarifa_hora, monto FROM registro_tiempo ORDER BY id_registro DESC LIMIT 1")[0]
    assert (float(fila["duracion_minutos"]) // 1, fila["tarifa_hora"]) == (90.0, Decimal("36000.00"))
    assert abs(fila["monto"] - Decimal("54000.00")) <= Decimal("30.00"), "90 minutos y unos segundos de ejecución"
    assert client.put("/api/tarifas/areas/1", json={"valor_hora": 99000}).status_code == 200
    assert mundo.consulta("SELECT monto FROM registro_tiempo ORDER BY id_registro DESC LIMIT 1")[0]["monto"] == fila["monto"]

    resumen = client.get("/api/control-horas/registros").get_json()["resumen"]
    assert float(resumen["monto_acumulado"]) == float(fila["monto"])
