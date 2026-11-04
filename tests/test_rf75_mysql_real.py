# -*- coding: utf-8 -*-
"""RF75 contra un MySQL real y desechable.

El monto de cada registro lo calcula la columna generada de `registro_tiempo`
(duración × tarifa congelada al iniciar). Estas pruebas comprueban que el reporte de
cobro lo suma sin recalcularlo: bordes del período, registros abiertos o de otro
cliente, y coincidencia con los totales de la pantalla de control de horas (RF73).
"""
import io
import os
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from tests.mysql_desechable import BASE_APP, herramientas_disponibles
from tests.test_rf74_mysql_real import mundo, servidor  # noqa: F401  (fixtures compartidas)

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)

# (id_cliente, fecha, hora_inicio, hora_fin, minutos, tarifa)
REGISTROS = [
    (1, "2026-09-30", "09:00:00", "10:00:00", "60.00", "30000.00"),   # un día antes del período
    (1, "2026-10-01", "09:00:00", "10:30:00", "90.00", "30000.00"),   # borde inicial
    (1, "2026-10-15", "09:00:00", "09:30:00", "30.00", "36000.00"),
    (1, "2026-10-31", "14:00:00", "14:45:00", "45.00", "36000.00"),   # borde final
    (1, "2026-11-01", "09:00:00", "11:00:00", "120.00", "36000.00"),  # un día después
    (2, "2026-10-10", "09:00:00", "12:00:00", "180.00", "30000.00"),  # otro cliente
    (1, "2026-10-12", "09:00:00", None, None, "30000.00"),            # registro abierto
]


@pytest.fixture
def con_registros(mundo, servidor):  # noqa: F811
    cn = servidor.conectar(base=BASE_APP)
    cur = cn.cursor()
    for id_cliente, fecha, inicio, fin, minutos, tarifa in REGISTROS:
        cur.execute(
            "INSERT INTO registro_tiempo (id_usuario, id_cliente, id_tarea, fecha, hora_inicio, hora_fin, "
            "duracion_minutos, tarifa_hora) VALUES (1, %s, 1, %s, %s, %s, %s, %s)",
            (id_cliente, fecha, inicio, fin, minutos, tarifa))
    cn.commit()
    cn.close()
    return mundo


def test_el_cobro_de_un_periodo_incluye_los_bordes_y_excluye_lo_demas(client, iniciar_sesion, con_registros):
    iniciar_sesion(usuario_id=1, rol_id=1)

    datos = client.get("/api/reportes/cobro-por-cliente",
                       query_string={"id_cliente": 1, "fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-31"}).get_json()

    # 90 min a 30.000 = 45.000 · 30 min a 36.000 = 18.000 · 45 min a 36.000 = 27.000
    assert [r["fecha"] for r in datos["registros"]] == ["2026-10-01", "2026-10-15", "2026-10-31"]
    assert datos["totales"] == {"horas": 2.75, "monto": 90000.0, "registros": 3}
    assert datos["desglose_por_tarifa"] == [
        {"tarifa_hora": 30000.0, "horas": 1.5, "monto": 45000.0},
        {"tarifa_hora": 36000.0, "horas": 1.25, "monto": 45000.0},
    ]
    esperado = con_registros.consulta(
        "SELECT SUM(monto) AS m FROM registro_tiempo WHERE id_cliente = 1 AND hora_fin IS NOT NULL "
        "AND fecha BETWEEN '2026-10-01' AND '2026-10-31'")[0]["m"]
    assert Decimal(str(datos["totales"]["monto"])) == esperado


def test_el_cobro_de_la_totalidad_cuadra_con_los_totales_del_control_de_horas(client, iniciar_sesion, con_registros):
    iniciar_sesion(usuario_id=1, rol_id=1)

    cobro = client.get("/api/reportes/cobro-por-cliente", query_string={"id_cliente": 1}).get_json()
    horas = client.get("/api/control-horas/registros").get_json()["resumen"]
    cliente = con_registros.consulta("SELECT razon_social FROM cliente WHERE id_cliente = 1")[0]["razon_social"]
    total_cliente = next(t for t in horas["totales_cliente"] if t["nombre"] == cliente)

    # Cinco registros cerrados: 30.000 + 45.000 + 18.000 + 27.000 + 72.000 en 345 minutos (el abierto y el otro cliente no cuentan).
    assert cobro["periodo"]["todos_los_registros"] is True and cobro["totales"]["registros"] == 5
    assert cobro["totales"]["monto"] == total_cliente["monto"] == 192000.0
    assert cobro["totales"]["horas"] == 5.75 and total_cliente["minutos"] == 345.0


def test_el_excel_exportado_suma_lo_mismo_que_la_pantalla(client, iniciar_sesion, con_registros):
    iniciar_sesion(usuario_id=1, rol_id=1)
    datos = client.get("/api/reportes/cobro-por-cliente",
                       query_string={"id_cliente": 1, "fecha_inicio": "2026-10-01", "fecha_fin": "2026-10-31"}).get_json()

    respuesta = client.get(f"/api/reportes/{datos['id_reporte']}/excel")

    libro = load_workbook(io.BytesIO(respuesta.data))
    filas = list(libro["Reporte"].values)[1:]
    assert len(filas) == 3 and sum(f[5] for f in filas) == datos["totales"]["monto"] == 90000.0
    assert dict(libro["Parámetros"].values)["Monto total a cobrar"] == "90.000 CLP"
    assert client.get(f"/api/reportes/{datos['id_reporte']}/pdf").status_code == 200


def test_un_usuario_de_area_no_puede_pedir_el_cobro(client, iniciar_sesion, con_registros):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)
    assert client.get("/api/reportes/cobro-por-cliente", query_string={"id_cliente": 1}).status_code == 403
