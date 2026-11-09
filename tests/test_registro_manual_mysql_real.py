"""Registro manual de horas contra un MySQL real y desechable.

Comprueba lo que una conexión simulada no puede: los solapes con marcas de
tiempo completas (incluidos los registros que cruzaron la medianoche y el
temporizador abierto), el plazo con el reloj de MySQL, el monto como columna
generada, la tarifa congelada, la atomicidad ante un fallo y dos envíos
simultáneos del mismo horario. Todos los registros se hacen en días ya
transcurridos, así que el resultado no depende de la hora de ejecución.
"""
import os
import threading
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.app import app as flask_app
from backend.routes import control_horas_routes
from tests.mysql_desechable import BASE_APP, herramientas_disponibles
from tests.test_rf74_mysql_real import mundo, servidor  # noqa: F401

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)

URL = "/api/control-horas/registros-manuales"
HOY = date.today()
AYER = HOY - timedelta(days=1)


@pytest.fixture
def entorno(mundo, servidor):  # noqa: F811
    """Datos del `mundo` (admin 1, jurídica 2, tarea 1 del admin) más tareas de apoyo."""
    cn = servidor.conectar(base=BASE_APP)
    cur = cn.cursor()
    cur.execute("INSERT INTO cliente (rut, razon_social, estado) VALUES ('33.333.333-3', 'Cliente Inactivo', 'INACTIVO')")
    base = ("INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, descripcion) "
            "VALUES (%s, %s, %s, 1, %s, 'Tarea de prueba')")
    cur.execute(base, (2, 1, 2, "Tarea de la jurídica"))        # id 2
    cur.execute(base, (1, 1, 1, "Tarea ya completada"))         # id 3
    cur.execute("UPDATE tarea SET estado = 'COMPLETADA', fecha_finalizacion = NOW() WHERE id_tarea = 3")
    cur.execute(base, (3, 1, 1, "Tarea de cliente inactivo"))   # id 4
    cn.commit()
    cn.close()
    return mundo


def _datos(**cambio):
    datos = {"id_tarea": 1, "fecha": AYER.isoformat(), "hora_inicio": "09:00", "hora_fin": "11:30",
             "observacion": "Visita a terreno"}
    datos.update(cambio)
    return datos


def _manuales(entorno):
    return entorno.consulta("SELECT * FROM registro_tiempo WHERE origen = 'MANUAL' ORDER BY id_registro")


def test_el_registro_manual_calcula_en_mysql_y_entra_al_historial_al_informe_y_al_cobro(client, iniciar_sesion, entorno):
    iniciar_sesion(usuario_id=1, rol_id=1)

    respuesta = client.post(URL, json=_datos())

    assert respuesta.status_code == 201, respuesta.get_json()
    fila = _manuales(entorno)[0]
    assert fila["duracion_minutos"] == Decimal("150.00")
    assert fila["tarifa_hora"] == Decimal("30000.00")
    assert fila["monto"] == Decimal("75000.00"), "el monto es la columna generada de MySQL"
    assert (fila["id_usuario"], fila["id_cliente"], fila["id_tarea"]) == (1, 1, 1)
    assert fila["origen"] == "MANUAL" and fila["observacion"] == "Visita a terreno"
    assert fila["hora_fin"] is not None and fila["fecha"] == AYER
    assert respuesta.get_json()["registro"]["monto"] == 75000.0

    historial = client.get("/api/control-horas/registros").get_json()
    assert [r["origen"] for r in historial["registros"]] == ["MANUAL"]
    assert historial["registros"][0]["observacion"] == "Visita a terreno"
    assert historial["resumen"]["minutos_acumulados"] == 150.0
    assert historial["resumen"]["monto_acumulado"] == 75000.0

    informe = client.get("/api/reportes/horas-trabajadas", query_string={"agrupar_por": "cliente"}).get_json()
    assert (informe["totales"]["horas"], informe["totales"]["monto"], informe["totales"]["registros"]) == (2.5, 75000.0, 1)
    cobro = client.get("/api/reportes/cobro-por-cliente", query_string={"id_cliente": 1}).get_json()
    assert cobro["totales"]["monto"] == 75000.0

    auditoria = entorno.consulta("SELECT * FROM auditoria WHERE accion = 'REGISTRO_MANUAL_CREADO'")
    assert len(auditoria) == 1
    assert (auditoria[0]["tabla_afectada"], auditoria[0]["id_registro"], auditoria[0]["id_usuario"]) == (
        "registro_tiempo", fila["id_registro"], 1)
    assert "Visita" not in (auditoria[0]["datos_nuevos"] or "")


def test_los_solapes_se_detectan_con_marcas_de_tiempo_y_los_horarios_contiguos_se_aceptan(client, iniciar_sesion, entorno):
    iniciar_sesion(usuario_id=1, rol_id=1)
    assert client.post(URL, json=_datos(hora_inicio="09:00", hora_fin="11:30")).status_code == 201

    for inicio, fin in (("11:00", "12:00"), ("08:00", "09:30"), ("09:30", "10:00"), ("08:00", "12:00"), ("09:00", "11:30")):
        respuesta = client.post(URL, json=_datos(hora_inicio=inicio, hora_fin=fin))
        assert respuesta.status_code == 409, (inicio, fin)
        assert "superpone" in respuesta.get_json()["error"]

    assert client.post(URL, json=_datos(hora_inicio="11:30", hora_fin="12:00")).status_code == 201, "empieza justo al terminar"
    assert client.post(URL, json=_datos(hora_inicio="08:00", hora_fin="09:00")).status_code == 201, "termina justo al empezar"
    assert client.post(URL, json=_datos(fecha=(AYER - timedelta(days=1)).isoformat())).status_code == 201, "otro día"
    assert len(_manuales(entorno)) == 4


def test_las_horas_de_otro_usuario_no_cuentan_para_el_solape(client, iniciar_sesion, entorno):
    iniciar_sesion(usuario_id=1, rol_id=1)
    assert client.post(URL, json=_datos()).status_code == 201

    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)
    assert client.post(URL, json=_datos(id_tarea=2)).status_code == 201

    assert {f["id_usuario"] for f in _manuales(entorno)} == {1, 2}


def test_el_temporizador_abierto_bloquea_solo_lo_que_se_superpone(client, iniciar_sesion, entorno, servidor):
    cn = servidor.conectar(base=BASE_APP)
    cur = cn.cursor()
    cur.execute("INSERT INTO registro_tiempo (id_usuario, id_cliente, id_tarea, fecha, hora_inicio, tarifa_hora) "
                "VALUES (1, 1, 1, %s, '20:00:00', 30000)", (AYER,))
    cn.commit()
    cn.close()
    iniciar_sesion(usuario_id=1, rol_id=1)

    for inicio, fin in (("20:00", "21:00"), ("21:00", "22:00"), ("19:30", "20:30")):
        respuesta = client.post(URL, json=_datos(hora_inicio=inicio, hora_fin=fin))
        assert respuesta.status_code == 409, (inicio, fin)
        assert "temporizador que tiene en curso" in respuesta.get_json()["error"]

    assert client.post(URL, json=_datos(hora_inicio="18:00", hora_fin="19:30")).status_code == 201
    assert client.post(URL, json=_datos(hora_inicio="19:30", hora_fin="20:00")).status_code == 201, "termina justo cuando empieza"
    assert client.post(URL, json=_datos(fecha=(AYER - timedelta(days=2)).isoformat(), hora_inicio="20:00", hora_fin="22:00")).status_code == 201


def test_un_registro_que_cruzo_la_medianoche_tambien_cuenta_para_el_solape(client, iniciar_sesion, entorno, servidor):
    dia = HOY - timedelta(days=4)
    cn = servidor.conectar(base=BASE_APP)
    cur = cn.cursor()
    # Un temporizador dejado de un día para otro: empezó a las 23:30 y se detuvo a las 00:30.
    cur.execute("INSERT INTO registro_tiempo (id_usuario, id_cliente, id_tarea, fecha, hora_inicio, hora_fin, "
                "duracion_minutos, tarifa_hora) VALUES (1, 1, 1, %s, '23:30:00', '00:30:00', 60, 30000)", (dia,))
    cn.commit()
    cn.close()
    iniciar_sesion(usuario_id=1, rol_id=1)
    siguiente = (dia + timedelta(days=1)).isoformat()

    assert client.post(URL, json=_datos(fecha=siguiente, hora_inicio="00:00", hora_fin="00:20")).status_code == 409
    assert client.post(URL, json=_datos(fecha=dia.isoformat(), hora_inicio="23:00", hora_fin="23:40")).status_code == 409
    assert client.post(URL, json=_datos(fecha=siguiente, hora_inicio="00:30", hora_fin="01:00")).status_code == 201
    assert client.post(URL, json=_datos(fecha=dia.isoformat(), hora_inicio="22:00", hora_fin="23:30")).status_code == 201


def test_el_plazo_de_30_dias_se_mide_con_la_fecha_de_mysql(client, iniciar_sesion, entorno):
    iniciar_sesion(usuario_id=1, rol_id=1)
    limite = HOY - timedelta(days=30)

    fuera = client.post(URL, json=_datos(fecha=(limite - timedelta(days=1)).isoformat()))
    assert fuera.status_code == 400 and "últimos 30 días" in fuera.get_json()["error"]
    assert client.post(URL, json=_datos(fecha=limite.isoformat())).status_code == 201
    assert client.post(URL, json=_datos(fecha=(HOY + timedelta(days=1)).isoformat())).status_code == 400
    assert len(_manuales(entorno)) == 1, "solo el del día 30; ni el 31 ni el de mañana"


@pytest.mark.parametrize(
    "usuario,rol,area,id_tarea,esperado",
    [
        (1, 1, 3, 1, 201),   # administrador, tarea propia
        (1, 1, 3, 2, 201),   # administrador en una tarea de otra persona
        (1, 1, 3, 3, 404),   # tarea completada
        (1, 1, 3, 4, 404),   # cliente inactivo
        (1, 1, 3, 999, 404),  # no existe
        (2, 2, 1, 2, 201),   # jurídica en su tarea
        (2, 2, 1, 1, 404),   # jurídica en la tarea del administrador
    ],
)
def test_solo_se_registra_en_tareas_activas_de_clientes_activos_y_permitidas(
    client, iniciar_sesion, entorno, usuario, rol, area, id_tarea, esperado
):
    iniciar_sesion(usuario_id=usuario, rol_id=rol, area_id=area)

    assert client.post(URL, json=_datos(id_tarea=id_tarea)).status_code == esperado
    assert len(_manuales(entorno)) == (1 if esperado == 201 else 0)


def test_la_tarifa_vigente_al_registrar_queda_congelada(client, iniciar_sesion, entorno):
    iniciar_sesion(usuario_id=1, rol_id=1)
    assert client.put("/api/tarifas/areas/1", json={"valor_hora": 40000}).status_code == 200
    assert client.post(URL, json=_datos()).status_code == 201
    assert client.put("/api/tarifas/areas/1", json={"valor_hora": 50000}).status_code == 200
    assert client.post(URL, json=_datos(hora_inicio="12:00", hora_fin="13:00")).status_code == 201

    filas = _manuales(entorno)
    assert [(f["tarifa_hora"], f["monto"]) for f in filas] == [
        (Decimal("40000.00"), Decimal("100000.00")),
        (Decimal("50000.00"), Decimal("50000.00")),
    ]


def test_el_temporizador_sigue_igual_y_sus_registros_quedan_como_del_temporizador(client, iniciar_sesion, entorno):
    iniciar_sesion(usuario_id=1, rol_id=1)

    assert client.post("/api/control-horas/iniciar", json={"id_tarea": 1}).status_code == 201
    assert client.post(URL, json=_datos()).status_code == 201, "se puede registrar el pasado con un temporizador en curso"
    assert client.post("/api/control-horas/detener").status_code == 200

    filas = entorno.consulta("SELECT origen, observacion, hora_fin IS NOT NULL AS cerrado FROM registro_tiempo ORDER BY id_registro")
    # El temporizador se inició primero (id menor) y se cerró al final.
    assert [(f["origen"], f["observacion"], f["cerrado"]) for f in filas] == [
        ("TEMPORIZADOR", None, 1),
        ("MANUAL", "Visita a terreno", 1),
    ]
    historial = client.get("/api/control-horas/registros").get_json()["registros"]
    assert {r["origen"] for r in historial} == {"MANUAL", "TEMPORIZADOR"}


def test_si_falla_la_auditoria_no_queda_ningun_registro(client, iniciar_sesion, entorno, monkeypatch):
    iniciar_sesion(usuario_id=1, rol_id=1)

    def fallar(*argumentos, **claves):
        raise RuntimeError("fallo simulado de la auditoría")

    monkeypatch.setattr(control_horas_routes, "registrar_auditoria", fallar)
    respuesta = client.post(URL, json=_datos())

    assert respuesta.status_code == 500
    assert _manuales(entorno) == [], "el registro y su auditoría van en la misma transacción"
    assert entorno.consulta("SELECT COUNT(*) AS n FROM auditoria")[0]["n"] == 0


def test_dos_envios_simultaneos_del_mismo_horario_registran_solo_uno(client, iniciar_sesion, entorno):
    iniciar_sesion(usuario_id=1, rol_id=1)
    barrera = threading.Barrier(2)
    estados = []

    def enviar():
        cliente = flask_app.test_client()
        with cliente.session_transaction() as sesion:
            sesion.update({"usuario_id": 1, "rol_id": 1, "area_id": 3, "nombre": "Usuario Prueba"})
        barrera.wait()
        estados.append(cliente.post(URL, json=_datos()).status_code)

    hilos = [threading.Thread(target=enviar) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)

    assert sorted(estados) == [201, 409]
    assert len(_manuales(entorno)) == 1
