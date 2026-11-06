"""C1/C2 contra MySQL desechable: agregados, límites y separación por usuario."""
import os
from decimal import Decimal

import pytest

from tests.mysql_desechable import BASE_APP, herramientas_disponibles
from tests.test_rf74_mysql_real import mundo, servidor  # noqa: F401

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)


@pytest.fixture
def con_registros(mundo, servidor):  # noqa: F811
    conexion = servidor.conectar(base=BASE_APP)
    cursor = conexion.cursor()
    cursor.execute(
        "INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) "
        "VALUES (3, 2, 'Usuaria Contable Ficticia', 'contable-ficticia@ejemplo.invalid', 'hash-ficticio-3')"
    )
    cursor.execute(
        "INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, descripcion) "
        "VALUES (2, 2, 3, 3, 'Tarea contable ficticia', 'Tarea de prueba')"
    )
    cursor.execute(
        "UPDATE tarea SET estado = 'COMPLETADA', fecha_finalizacion = '2026-10-01 10:00:00' "
        "WHERE id_tarea = 1"
    )

    registros = [
        (1, 1, 1, "2026-09-30", "09:00:00", "09:30:00", "30.00", "30000.00"),
        (2, 1, 1, "2026-10-01", "09:00:00", "10:00:00", "60.00", "30000.00"),
        (3, 2, 2, "2026-10-31", "09:00:00", "10:30:00", "90.00", "36000.00"),
        (1, 2, 2, "2026-11-01", "09:00:00", "11:00:00", "120.00", "36000.00"),
        (2, 1, 1, "2026-10-15", "13:00:00", None, None, "30000.00"),
    ]
    cursor.executemany(
        "INSERT INTO registro_tiempo "
        "(id_usuario, id_cliente, id_tarea, fecha, hora_inicio, hora_fin, duracion_minutos, tarifa_hora) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        registros,
    )
    conexion.commit()
    conexion.close()
    return mundo


def _totales(datos):
    return datos["totales"]["horas"], datos["totales"]["monto"], datos["totales"]["registros"]


def test_agrupaciones_control_y_cobro_coinciden_con_sql_directo(
    client, iniciar_sesion, con_registros
):
    iniciar_sesion(usuario_id=1, rol_id=1)
    esperado = con_registros.consulta(
        "SELECT SUM(duracion_minutos) AS minutos, SUM(monto) AS monto, COUNT(*) AS registros "
        "FROM registro_tiempo WHERE hora_fin IS NOT NULL"
    )[0]
    assert esperado == {
        "minutos": Decimal("300.00"),
        "monto": Decimal("171000.00"),
        "registros": 4,
    }

    agrupaciones = [
        {"agrupar_por": "cliente"},
        {"agrupar_por": "tarea"},
        {"agrupar_por": "usuario"},
        {"agrupar_por": "periodo", "granularidad": "dia"},
        {"agrupar_por": "periodo", "granularidad": "mes"},
    ]
    for parametros in agrupaciones:
        respuesta = client.get("/api/reportes/horas-trabajadas", query_string=parametros)
        assert respuesta.status_code == 200
        assert _totales(respuesta.get_json()) == (5.0, 171000.0, 4)

    historial = client.get("/api/control-horas/registros")
    assert historial.status_code == 200
    datos_historial = historial.get_json()
    assert len(datos_historial["registros"]) == esperado["registros"]
    assert datos_historial["resumen"]["minutos_acumulados"] == float(esperado["minutos"])
    assert datos_historial["resumen"]["monto_acumulado"] == float(esperado["monto"])
    assert datos_historial["resumen"]["total_registros"] == esperado["registros"]

    monto_cobros = Decimal("0")
    for id_cliente in (1, 2):
        cobro = client.get(
            "/api/reportes/cobro-por-cliente",
            query_string={"id_cliente": id_cliente},
        )
        assert cobro.status_code == 200
        monto_cobros += Decimal(str(cobro.get_json()["totales"]["monto"]))
    assert monto_cobros == esperado["monto"]


def test_fechas_inclusivas_registro_abierto_y_tarea_completada(
    client, iniciar_sesion, con_registros
):
    iniciar_sesion(usuario_id=1, rol_id=1)

    respuesta = client.get(
        "/api/reportes/horas-trabajadas",
        query_string={
            "agrupar_por": "cliente",
            "fecha_inicio": "2026-10-01",
            "fecha_fin": "2026-10-31",
        },
    )
    assert respuesta.status_code == 200
    assert _totales(respuesta.get_json()) == (2.5, 84000.0, 2)

    filtros = client.get("/api/control-horas/filtros")
    assert filtros.status_code == 200
    datos_filtros = filtros.get_json()
    tareas = {tarea["id_tarea"]: tarea for tarea in datos_filtros["tareas"]}
    assert tareas[1]["titulo"] == "Declaración «Renta» 2026"
    assert {cliente["id_cliente"] for cliente in datos_filtros["clientes"]} == {1, 2}

    abiertos = con_registros.consulta(
        "SELECT COUNT(*) AS total FROM registro_tiempo WHERE hora_fin IS NULL"
    )
    assert abiertos[0]["total"] == 1


@pytest.mark.parametrize(
    ("usuario_id", "rol_id", "id_cliente", "id_tarea"),
    [(2, 2, 1, 1), (3, 3, 2, 2)],
)
def test_catalogos_e_historial_operativos_solo_exponen_registros_propios(
    client,
    iniciar_sesion,
    con_registros,
    usuario_id,
    rol_id,
    id_cliente,
    id_tarea,
):
    iniciar_sesion(usuario_id=usuario_id, rol_id=rol_id, area_id=rol_id - 1)

    filtros = client.get("/api/control-horas/filtros")
    assert filtros.status_code == 200
    datos_filtros = filtros.get_json()
    assert datos_filtros["usuarios"] == []
    assert {cliente["id_cliente"] for cliente in datos_filtros["clientes"]} == {id_cliente}
    assert {tarea["id_tarea"] for tarea in datos_filtros["tareas"]} == {id_tarea}

    historial = client.get("/api/control-horas/registros")
    assert historial.status_code == 200
    registros = historial.get_json()["registros"]
    assert len(registros) == 1
    assert registros[0]["usuario_responsable"] in {
        "Usuaria Jurídica",
        "Usuaria Contable Ficticia",
    }
    assert all(registro["cliente"] != "Cliente Dos" for registro in registros) == (usuario_id == 2)
