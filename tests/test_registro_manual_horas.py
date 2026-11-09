"""Registro manual de horas (CU-14 y CU-29): POST /api/control-horas/registros-manuales.

Estas pruebas usan una conexión simulada y fijan el reloj de MySQL, así que no
dependen de la hora en que se ejecuten. La variante con un MySQL real y
desechable (solapes, medianoche, cobro) está en test_registro_manual_mysql_real.py.
"""
import copy
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

import backend.routes.control_horas_routes as control_horas_routes
from tests.conftest import normalize_sql

URL = "/api/control-horas/registros-manuales"
AHORA = datetime(2026, 11, 8, 15, 30, 0)
HOY = AHORA.date().isoformat()
AYER = (AHORA.date() - timedelta(days=1)).isoformat()

DATOS_VALIDOS = {
    "id_tarea": 12,
    "fecha": AYER,
    "hora_inicio": "09:00",
    "hora_fin": "11:30",
    "observacion": "Visita a terreno",
}


def _manejador(estado, capturado):
    def manejar(sql, params, cursor):
        sql_normalizado = normalize_sql(sql)
        capturado.append((sql_normalizado, params))

        if "FROM usuario u INNER JOIN rol r" in sql_normalizado:
            return [{
                "id_usuario": params[0],
                "estado": estado.get("estado_usuario", "ACTIVO"),
                "nombre_rol": estado.get("rol", "USUARIO_AREA_JURIDICA"),
            }]
        if "SELECT CURRENT_TIMESTAMP AS ahora" in sql_normalizado:
            return [{"ahora": estado.get("ahora", AHORA)}]
        if "SELECT t.id_tarea, t.id_cliente, t.id_area" in sql_normalizado:
            if estado.get("sin_tarea"):
                return []
            return [{"id_tarea": params[0], "id_cliente": 7, "id_area": 1}]
        if "FROM registro_tiempo rt WHERE rt.id_usuario" in sql_normalizado:
            return [estado["solape"]] if estado.get("solape") else []
        if "FROM tarifa_hora" in sql_normalizado:
            return [{"valor_hora": Decimal("30000.00")}]
        if "INSERT INTO registro_tiempo" in sql_normalizado:
            cursor.lastrowid = 55
            return []
        if "WHERE rt.id_registro = %s" in sql_normalizado:
            return [{
                "id_registro": 55,
                "duracion_minutos": Decimal("150.00"),
                "tarifa_hora": Decimal("30000.00"),
                "monto": Decimal("75000.00"),
                "origen": "MANUAL",
                "observacion": "Visita a terreno",
                "tarea": "Declaración mensual",
                "descripcion": "",
                "cliente": "Cliente de prueba",
                "fecha": "07-11-2026",
                "inicio": "09:00:00",
                "fin": "11:30:00",
            }]
        if "AS minutos_acumulados" in sql_normalizado:
            return [{
                "minutos_acumulados": Decimal("150.00"),
                "monto_acumulado": Decimal("75000.00"),
                "minutos_hoy": Decimal("0"),
                "total_registros": 1,
            }]
        return []

    return manejar


@pytest.fixture
def registrar(client, iniciar_sesion, fake_connection_factory, monkeypatch):
    def _registrar(datos=None, rol_id=2, **estado):
        nombres = {1: "ADMINISTRADOR", 2: "USUARIO_AREA_JURIDICA", 3: "USUARIO_AREA_CONTABLE"}
        estado.setdefault("rol", nombres[rol_id])
        capturado = []
        conexion = fake_connection_factory(_manejador(estado, capturado))
        monkeypatch.setattr(control_horas_routes, "get_connection", lambda: conexion)
        iniciar_sesion(usuario_id=4, rol_id=rol_id)
        cuerpo = copy.deepcopy(DATOS_VALIDOS if datos is None else datos)
        respuesta = client.post(URL, json=cuerpo)
        return respuesta, capturado, conexion

    return _registrar


def _insercion(capturado):
    return next(((sql, p) for sql, p in capturado if sql.startswith("INSERT INTO registro_tiempo")), None)


def test_registrar_horas_manualmente_responde_201_y_guarda_el_registro_cerrado(registrar):
    respuesta, capturado, conexion = registrar()

    assert respuesta.status_code == 201
    datos = respuesta.get_json()
    assert datos["message"] == "Horas registradas manualmente correctamente."
    assert datos["registro"]["origen"] == "MANUAL"
    assert datos["registro"]["monto"] == 75000.0
    assert datos["registro"]["duracion_minutos"] == 150.0
    assert datos["resumen"]["total_registros"] == 1

    sql, parametros = _insercion(capturado)
    assert "'MANUAL'" in sql and "hora_fin" in sql
    (id_usuario, id_cliente, id_tarea, fecha, hora_inicio, hora_fin,
     duracion, tarifa, observacion) = parametros
    assert (id_usuario, id_cliente, id_tarea) == (4, 7, 12)
    assert (fecha.isoformat(), hora_inicio.strftime("%H:%M"), hora_fin.strftime("%H:%M")) == (AYER, "09:00", "11:30")
    assert duracion == Decimal("150.00")
    assert tarifa == Decimal("30000.00")
    assert observacion == "Visita a terreno"
    assert conexion.commits == 1 and conexion.rollbacks == 0
    assert any("FOR UPDATE" in sql for sql, _ in capturado), "serializa con iniciar/detener bloqueando al usuario"


def test_duracion_tarifa_y_monto_los_calcula_el_servidor_aunque_el_cliente_los_envie(registrar):
    datos = dict(DATOS_VALIDOS, duracion_minutos=99999, tarifa_hora=1, monto=1, origen="TEMPORIZADOR", id_usuario=1)
    respuesta, capturado, _ = registrar(datos)

    assert respuesta.status_code == 201
    sql, parametros = _insercion(capturado)
    assert parametros[0] == 4, "el registro es siempre del usuario de la sesión"
    assert parametros[6] == Decimal("150.00") and parametros[7] == Decimal("30000.00")
    assert "'MANUAL'" in sql


def test_la_observacion_se_guarda_en_una_linea_y_no_se_copia_a_la_auditoria(registrar):
    datos = dict(DATOS_VALIDOS, observacion="  Reunión \n con   el cliente\t<b>importante</b>  ")
    respuesta, capturado, _ = registrar(datos)

    assert respuesta.status_code == 201
    _, parametros = _insercion(capturado)
    assert parametros[8] == "Reunión con el cliente <b>importante</b>"
    auditoria = next(p for sql, p in capturado if sql.startswith("INSERT INTO auditoria"))
    assert auditoria[:4] == (4, "registro_tiempo", 55, "REGISTRO_MANUAL_CREADO")
    assert "importante" not in auditoria[5] and "Reunión" not in auditoria[5]
    assert f"fecha={AYER}" in auditoria[5] and "hora_inicio=09:00" in auditoria[5]


@pytest.mark.parametrize(
    "cambio,fragmento",
    [
        ({"id_tarea": None}, "tarea válida"),
        # Estos dos los rechaza antes la validación global de identificadores (app.py).
        ({"id_tarea": 0}, "id_tarea"),
        ({"id_tarea": "abc"}, "id_tarea"),
        ({"fecha": "08-11-2026"}, "fecha no es válida"),
        ({"fecha": "2026-02-30"}, "fecha no es válida"),
        ({"fecha": 20261108}, "fecha no es válida"),
        ({"hora_inicio": "25:00"}, "no son válidas"),
        ({"hora_inicio": None}, "no son válidas"),
        ({"hora_fin": "mediodía"}, "no son válidas"),
        ({"hora_fin": "09:00"}, "posterior"),
        ({"hora_fin": "08:00"}, "posterior"),
        ({"observacion": ""}, "observación"),
        ({"observacion": "   \n\t "}, "observación"),
        ({"observacion": None}, "observación"),
        ({"observacion": 1234}, "observación"),
        ({"observacion": "x" * 256}, "255 caracteres"),
    ],
)
def test_datos_invalidos_responden_400_sin_abrir_la_base_de_datos(
    client, iniciar_sesion, monkeypatch, cambio, fragmento
):
    abierta = []
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: abierta.append(1))
    iniciar_sesion(usuario_id=4, rol_id=2)

    datos = {**DATOS_VALIDOS, **cambio}
    respuesta = client.post(URL, json=datos)

    assert respuesta.status_code == 400
    assert fragmento in respuesta.get_json()["error"]
    assert abierta == [], "una entrada mal formada no debe consultar ni bloquear nada"


@pytest.mark.parametrize("campo", ["id_tarea", "fecha", "hora_inicio", "hora_fin", "observacion"])
def test_cada_campo_es_obligatorio(client, iniciar_sesion, monkeypatch, campo):
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: pytest.fail("no debía abrirse"))
    iniciar_sesion(usuario_id=4, rol_id=2)
    datos = {k: v for k, v in DATOS_VALIDOS.items() if k != campo}

    assert client.post(URL, json=datos).status_code == 400


@pytest.mark.parametrize("cuerpo", [[], "texto", 7, None])
def test_un_cuerpo_json_que_no_es_un_objeto_responde_400(client, iniciar_sesion, monkeypatch, cuerpo):
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: pytest.fail("no debía abrirse"))
    iniciar_sesion(usuario_id=4, rol_id=2)

    assert client.post(URL, json=cuerpo).status_code == 400


def test_sin_cuerpo_ni_tipo_json_responde_400_y_con_tipo_json_vacio_tambien(client, iniciar_sesion, monkeypatch):
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: pytest.fail("no debía abrirse"))
    iniciar_sesion(usuario_id=4, rol_id=2)

    assert client.post(URL).status_code == 400
    assert client.post(URL, data="", content_type="application/json").status_code == 400
    assert client.post(URL, data="{no es json", content_type="application/json").status_code == 400


def test_exige_sesion(client):
    respuesta = client.post(URL, json=DATOS_VALIDOS)

    assert respuesta.status_code == 401


def test_horas_futuras_se_rechazan_con_el_reloj_de_mysql(registrar):
    manana = dict(DATOS_VALIDOS, fecha=(AHORA.date() + timedelta(days=1)).isoformat())
    respuesta, capturado, conexion = registrar(manana)
    assert respuesta.status_code == 400 and "todavía no ocurrieron" in respuesta.get_json()["error"]
    assert _insercion(capturado) is None and conexion.commits == 0

    # Hoy, pero la hora de término es posterior a «ahora» (15:30).
    hoy_futuro = dict(DATOS_VALIDOS, fecha=HOY, hora_inicio="15:00", hora_fin="15:31")
    respuesta, capturado, _ = registrar(hoy_futuro)
    assert respuesta.status_code == 400 and _insercion(capturado) is None

    # Hoy y ya terminado: se acepta, incluido terminar justo «ahora».
    for fin in ("14:00", "15:30"):
        hoy_pasado = dict(DATOS_VALIDOS, fecha=HOY, hora_inicio="13:00", hora_fin=fin)
        respuesta, _, _ = registrar(hoy_pasado)
        assert respuesta.status_code == 201, fin


def test_el_plazo_retroactivo_es_de_30_dias(registrar):
    limite = (AHORA.date() - timedelta(days=control_horas_routes.DIAS_MAXIMOS_RETROACTIVO)).isoformat()
    antes = (AHORA.date() - timedelta(days=control_horas_routes.DIAS_MAXIMOS_RETROACTIVO + 1)).isoformat()

    respuesta, capturado, conexion = registrar(dict(DATOS_VALIDOS, fecha=antes))
    assert respuesta.status_code == 400 and "últimos 30 días" in respuesta.get_json()["error"]
    assert _insercion(capturado) is None and conexion.rollbacks == 1

    respuesta, _, _ = registrar(dict(DATOS_VALIDOS, fecha=limite))
    assert respuesta.status_code == 201, "el día 30 todavía se acepta"
    assert control_horas_routes.DIAS_MAXIMOS_RETROACTIVO == 30


@pytest.mark.parametrize("rol", ["OTRO_ROL", None])
def test_un_rol_no_habilitado_recibe_403(registrar, rol):
    respuesta, capturado, conexion = registrar(rol=rol or "SIN_ROL_CONOCIDO")

    assert respuesta.status_code == 403
    assert _insercion(capturado) is None and conexion.rollbacks == 1 and conexion.commits == 0


def test_un_usuario_inactivo_recibe_403_y_no_se_inserta_nada(registrar):
    respuesta, capturado, conexion = registrar(estado_usuario="INACTIVO")

    assert respuesta.status_code == 403
    assert "usuario activo" in respuesta.get_json()["error"]
    assert _insercion(capturado) is None and conexion.commits == 0


def test_una_tarea_no_disponible_responde_404(registrar):
    respuesta, capturado, conexion = registrar(sin_tarea=True)

    assert respuesta.status_code == 404
    assert "no está disponible" in respuesta.get_json()["error"]
    assert _insercion(capturado) is None and conexion.rollbacks == 1


def test_un_usuario_de_area_solo_registra_en_sus_propias_tareas_y_el_administrador_en_cualquiera(registrar):
    _, capturado, _ = registrar(rol_id=2)
    consulta, parametros = next(
        (sql, p) for sql, p in capturado if "SELECT t.id_tarea, t.id_cliente, t.id_area" in sql
    )
    assert "t.id_responsable = %s" in consulta and parametros == (12, 4)
    assert "c.estado = 'ACTIVO'" in consulta and "t.estado IN" in consulta

    _, capturado, _ = registrar(rol_id=1)
    consulta, parametros = next(
        (sql, p) for sql, p in capturado if "SELECT t.id_tarea, t.id_cliente, t.id_area" in sql
    )
    assert "t.id_responsable" not in consulta and parametros == (12,)


def test_un_solape_con_horas_ya_registradas_responde_409_sin_insertar(registrar):
    solape = {"en_curso": 0, "desde": "07-11-2026 08:00", "hasta": "07-11-2026 10:00"}
    respuesta, capturado, conexion = registrar(solape=solape)

    assert respuesta.status_code == 409
    mensaje = respuesta.get_json()["error"]
    assert "superpone" in mensaje and "07-11-2026 08:00 a 07-11-2026 10:00" in mensaje
    assert _insercion(capturado) is None and conexion.rollbacks == 1 and conexion.commits == 0


def test_un_solape_con_el_temporizador_en_curso_responde_409_con_su_propio_mensaje(registrar):
    solape = {"en_curso": 1, "desde": "07-11-2026 10:00", "hasta": "07-11-2026 10:00"}
    respuesta, capturado, _ = registrar(solape=solape)

    assert respuesta.status_code == 409
    assert "temporizador que tiene en curso" in respuesta.get_json()["error"]
    assert _insercion(capturado) is None


def test_la_consulta_de_solape_compara_marcas_de_tiempo_completas_y_cuenta_el_temporizador_abierto(registrar):
    _, capturado, _ = registrar()
    consulta, parametros = next(
        (sql, p) for sql, p in capturado if "FROM registro_tiempo rt WHERE rt.id_usuario" in sql
    )

    assert "TIMESTAMP(rt.fecha, rt.hora_inicio) < %s" in consulta
    assert "rt.hora_fin IS NULL" in consulta, "un temporizador abierto ocupa hasta ahora"
    assert "TIMESTAMPADD( SECOND, ROUND(rt.duracion_minutos * 60)" in consulta
    id_usuario, fin, inicio = parametros
    assert id_usuario == 4
    assert (inicio, fin) == (datetime.fromisoformat(f"{AYER}T09:00:00"), datetime.fromisoformat(f"{AYER}T11:30:00"))


def test_un_error_inesperado_devuelve_500_con_rollback_y_sin_detalles(client, iniciar_sesion, monkeypatch):
    class ConexionRota:
        rollbacks = 0

        def start_transaction(self):
            raise RuntimeError("detalle interno que no debe filtrarse")

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            pass

    conexion = ConexionRota()
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: conexion)
    iniciar_sesion(usuario_id=4, rol_id=2)

    respuesta = client.post(URL, json=DATOS_VALIDOS)

    assert respuesta.status_code == 500
    assert "detalle interno" not in respuesta.get_data(as_text=True)
    assert conexion.rollbacks == 1


def test_el_historial_devuelve_origen_y_observacion(client, iniciar_sesion, fake_connection_factory, monkeypatch):
    consultas = []

    def manejar(sql, params, cursor):
        consultas.append(normalize_sql(sql))
        if "FROM usuario u INNER JOIN rol r" in normalize_sql(sql):
            return [{"id_usuario": 4, "estado": "ACTIVO", "nombre_rol": "USUARIO_AREA_JURIDICA"}]
        return []

    conexion = fake_connection_factory(manejar)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: conexion)
    iniciar_sesion(usuario_id=4, rol_id=2)

    assert client.get("/api/control-horas/registros").status_code == 200
    listado = next(sql for sql in consultas if "u.nombres AS usuario_responsable" in sql)
    assert "rt.origen" in listado and "rt.observacion" in listado
