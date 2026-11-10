# -*- coding: utf-8 -*-
"""D1 (protecciones técnicas del temporizador) y D2 (anulación lógica de horas) con MySQL real desechable.

Datos ficticios; nunca el puerto 3306. D3 (facturación): el sistema no guarda si un registro fue facturado,
así que NO hay bloqueo por «facturado»; `test_d3_...` fija esa limitación para que no pase inadvertida.
"""
import io
import os
import re
import threading

import pytest
from openpyxl import load_workbook

from backend.app import app as flask_app
from backend.routes import control_horas_routes as ch
from tests.mysql_desechable import herramientas_disponibles
from tests.test_cierre_rf_sin_prueba_mysql_real import mundo, servidor  # noqa: F401  (fixtures compartidas)

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)

ID_ADMIN, ID_JURIDICA, ID_CONTABLE = 1, 2, 3
MOTIVO = "Registro duplicado por error de digitación"


@pytest.fixture
def datos(mundo):  # noqa: F811
    """Usuario contable (área 2) con su tarea; tarea 1 es del administrador (área Jurídica)."""
    mundo.sql("INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) "
              "VALUES (3, 2, 'Contable Ficticio', 'c@ejemplo.invalid', 'x')")
    mundo.sql("INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, fecha_vencimiento) "
              "VALUES (2, 2, 3, 1, 'Tarea contable', '2030-01-01')")
    return mundo


def _sesion(cliente, iniciar_sesion, usuario, rol, area):
    iniciar_sesion(usuario_id=usuario, rol_id=rol, area_id=area, nombre=f"Usuario {usuario}")


def _fila(mundo, id_registro):
    return mundo.sql("SELECT * FROM registro_tiempo WHERE id_registro = %s", (id_registro,), filas=True)[0]


def _manual(mundo, id_usuario, id_tarea, id_cliente, minutos=60, dias_atras=1, hora="09:00:00"):
    """Inserta un registro cerrado ya valorizado (60 min × 30.000 = 30.000 por defecto)."""
    mundo.sql(
        "INSERT INTO registro_tiempo (id_usuario, id_cliente, id_tarea, fecha, hora_inicio, hora_fin, duracion_minutos, "
        "tarifa_hora, origen, observacion) VALUES (%s, %s, %s, CURDATE() - INTERVAL %s DAY, %s, "
        "ADDTIME(%s, SEC_TO_TIME(%s * 60)), %s, 30000, 'MANUAL', 'Trabajo ficticio')",
        (id_usuario, id_cliente, id_tarea, dias_atras, hora, hora, minutos, minutos))
    return mundo.sql("SELECT MAX(id_registro) AS i FROM registro_tiempo", filas=True)[0]["i"]


def _retroceder_abierto(mundo, minutos):
    mundo.sql("UPDATE registro_tiempo SET fecha = DATE(NOW() - INTERVAL %s MINUTE), "
              "hora_inicio = TIME(NOW() - INTERVAL %s MINUTE) WHERE hora_fin IS NULL", (minutos, minutos))


def _auditoria(mundo, accion):
    return mundo.sql("SELECT * FROM auditoria WHERE accion = %s ORDER BY id_auditoria", (accion,), filas=True)


# ============================================================ D1 · temporizador
def test_d1_el_umbral_de_aviso_es_configurable_y_se_puede_desactivar(monkeypatch):
    monkeypatch.delenv("TEMPORIZADOR_AVISO_HORAS", raising=False)
    assert ch.umbral_aviso_minutos() == 12 * 60
    for valor, esperado in (("2", 120), ("0.5", 30), ("0", None), ("-3", None), ("abc", 720), ("", 720)):
        monkeypatch.setenv("TEMPORIZADOR_AVISO_HORAS", valor)
        assert ch.umbral_aviso_minutos() == esperado, valor


def test_d1_una_duracion_anomala_pide_confirmacion_sin_cerrar_ni_descartar_nada(client, iniciar_sesion, datos):
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    assert client.post("/api/control-horas/iniciar", json={"id_tarea": 1}).status_code == 201
    _retroceder_abierto(datos, 13 * 60)

    r = client.post("/api/control-horas/detener")
    assert r.status_code == 409
    cuerpo = r.get_json()
    assert cuerpo["codigo"] == "DURACION_ANOMALA" and cuerpo["umbral_horas"] == 12
    assert 12.9 * 60 < cuerpo["minutos_transcurridos"] < 13.1 * 60
    abierto = datos.sql("SELECT hora_fin, duracion_minutos FROM registro_tiempo", filas=True)[0]
    assert abierto == {"hora_fin": None, "duracion_minutos": None}, "no se cierra ni se registra nada"
    assert _auditoria(datos, "TEMPORIZADOR_DETENIDO") == []
    # El temporizador sigue recuperable
    assert client.get("/api/control-horas/contexto").get_json()["temporizador_activo"]["id_registro"] == 1


def test_d1_confirmada_la_duracion_real_se_guarda_completa_sin_tope_ni_recorte(client, iniciar_sesion, datos):
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    client.post("/api/control-horas/iniciar", json={"id_tarea": 1})
    _retroceder_abierto(datos, 13 * 60)

    r = client.post("/api/control-horas/detener", json={"confirmar_duracion": True})
    assert r.status_code == 200, r.get_json()
    fila = _fila(datos, 1)
    assert 779 < float(fila["duracion_minutos"]) < 781, "la duración real (≈13 h) queda guardada sin recortes"
    assert abs(float(fila["monto"]) - float(fila["duracion_minutos"]) / 60 * 30000) < 0.01, "el cobro no cambia"
    eventos = _auditoria(datos, "TEMPORIZADOR_DETENIDO")
    assert len(eventos) == 1 and "duracion_anomala_confirmada=si" in eventos[0]["datos_nuevos"]


def test_d1_una_confirmacion_que_no_es_verdadera_no_cuenta(client, iniciar_sesion, datos):
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    client.post("/api/control-horas/iniciar", json={"id_tarea": 1})
    _retroceder_abierto(datos, 13 * 60)
    for valor in ("true", 1, "si", None):
        assert client.post("/api/control-horas/detener", json={"confirmar_duracion": valor}).status_code == 409


def test_d1_el_umbral_cambia_con_la_configuracion_y_desactivado_no_advierte(client, iniciar_sesion, datos, monkeypatch):
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    client.post("/api/control-horas/iniciar", json={"id_tarea": 1})
    _retroceder_abierto(datos, 120)
    monkeypatch.setenv("TEMPORIZADOR_AVISO_HORAS", "1")
    assert client.post("/api/control-horas/detener").status_code == 409
    assert client.get("/api/control-horas/contexto").get_json()["umbral_aviso_horas"] == 1
    monkeypatch.setenv("TEMPORIZADOR_AVISO_HORAS", "0")
    assert client.get("/api/control-horas/contexto").get_json()["umbral_aviso_horas"] is None
    assert client.post("/api/control-horas/detener").status_code == 200  # desactivado: comportamiento anterior


def test_d1_bajo_el_umbral_nada_cambia_y_el_calculo_de_cobro_es_el_de_siempre(client, iniciar_sesion, datos):
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    client.post("/api/control-horas/iniciar", json={"id_tarea": 1})
    _retroceder_abierto(datos, 90)
    r = client.post("/api/control-horas/detener")
    assert r.status_code == 200 and round(r.get_json()["registro"]["monto"]) == 45000


def test_d1_inicios_simultaneos_del_mismo_usuario_crean_un_solo_temporizador(iniciar_sesion, client, datos):
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    resultados = []

    def lanzar():
        c = flask_app.test_client()
        with c.session_transaction() as s:
            s["usuario_id"], s["rol_id"], s["area_id"] = ID_ADMIN, 1, 3
        resultados.append(c.post("/api/control-horas/iniciar", json={"id_tarea": 1}).status_code)

    hilos = [threading.Thread(target=lanzar) for _ in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sorted(resultados) == [201] + [409] * 7
    assert datos.sql("SELECT COUNT(*) n FROM registro_tiempo WHERE hora_fin IS NULL", filas=True)[0]["n"] == 1


def test_d1_cierres_simultaneos_registran_una_sola_vez(iniciar_sesion, client, datos):
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    client.post("/api/control-horas/iniciar", json={"id_tarea": 1})
    resultados = []

    def lanzar():
        c = flask_app.test_client()
        with c.session_transaction() as s:
            s["usuario_id"], s["rol_id"], s["area_id"] = ID_ADMIN, 1, 3
        resultados.append(c.post("/api/control-horas/detener").status_code)

    hilos = [threading.Thread(target=lanzar) for _ in range(6)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sorted(resultados) == [200] + [404] * 5
    assert len(_auditoria(datos, "TEMPORIZADOR_DETENIDO")) == 1
    assert datos.sql("SELECT COUNT(*) n FROM registro_tiempo", filas=True)[0]["n"] == 1


def test_d1_el_temporizador_se_recupera_tras_cerrar_el_navegador_o_caducar_la_sesion(client, iniciar_sesion, datos):
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    client.post("/api/control-horas/iniciar", json={"id_tarea": 1})
    with client.session_transaction() as s:
        s.clear()  # cookie perdida o sesión caducada
    assert client.get("/api/control-horas/contexto").status_code == 401
    assert client.post("/api/control-horas/detener").status_code == 401
    assert datos.sql("SELECT COUNT(*) n FROM registro_tiempo WHERE hora_fin IS NULL", filas=True)[0]["n"] == 1

    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)  # vuelve a entrar
    assert client.get("/api/control-horas/contexto").get_json()["temporizador_activo"]["id_registro"] == 1
    assert client.post("/api/control-horas/iniciar", json={"id_tarea": 1}).status_code == 409  # sin duplicados
    assert client.post("/api/control-horas/detener").status_code == 200


def test_d1_el_historial_marca_las_duraciones_muy_largas_sin_modificarlas(client, iniciar_sesion, datos, monkeypatch):
    _manual(datos, ID_ADMIN, 1, 1, minutos=13 * 60 - 1)
    _manual(datos, ID_ADMIN, 1, 1, minutos=30, dias_atras=3)
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    registros = client.get("/api/control-horas/registros").get_json()["registros"]
    assert sorted((round(r["duracion_minutos"]), r["aviso_duracion"]) for r in registros) == [(30, False), (779, True)]


# ============================================================== D2 · anulación
def test_d2_el_administrador_anula_conservando_el_original_y_deja_responsable_fecha_y_motivo(client, iniciar_sesion, datos):
    idr = _manual(datos, ID_JURIDICA, 1, 1, minutos=60)
    antes = _fila(datos, idr)
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    r = client.post(f"/api/control-horas/registros/{idr}/anular", json={"motivo": f"  {MOTIVO}  "})
    assert r.status_code == 200, r.get_json()
    despues = _fila(datos, idr)
    assert (despues["estado_registro"], despues["anulado_por"], despues["motivo_anulacion"]) == ("ANULADO", ID_ADMIN, MOTIVO)
    assert despues["fecha_anulacion"] is not None
    for campo in ("id_usuario", "id_cliente", "id_tarea", "fecha", "hora_inicio", "hora_fin", "duracion_minutos",
                  "tarifa_hora", "monto", "origen", "observacion"):
        assert despues[campo] == antes[campo], f"el original no debe cambiar: {campo}"
    assert datos.sql("SELECT COUNT(*) n FROM registro_tiempo", filas=True)[0]["n"] == 1, "sin eliminación física"


@pytest.mark.parametrize("rol,area", [(2, 1), (3, 2)])
def test_d2_un_usuario_de_area_no_puede_anular(client, iniciar_sesion, datos, rol, area):
    idr = _manual(datos, ID_JURIDICA, 1, 1)
    _sesion(client, iniciar_sesion, ID_JURIDICA if rol == 2 else ID_CONTABLE, rol, area)
    assert client.post(f"/api/control-horas/registros/{idr}/anular", json={"motivo": MOTIVO}).status_code == 403
    assert _fila(datos, idr)["estado_registro"] == "VIGENTE"
    assert _auditoria(datos, "REGISTRO_ANULADO") == []


def test_d2_sin_sesion_no_se_puede_anular(client, datos):
    idr = _manual(datos, ID_JURIDICA, 1, 1)
    assert client.post(f"/api/control-horas/registros/{idr}/anular", json={"motivo": MOTIVO}).status_code == 401
    assert _fila(datos, idr)["estado_registro"] == "VIGENTE"


@pytest.mark.parametrize("cuerpo", [{}, {"motivo": ""}, {"motivo": "   "}, {"motivo": "corto"}, {"motivo": 12345678901},
                                    {"motivo": None}, {"motivo": "x" * 256}])
def test_d2_el_motivo_es_obligatorio_y_acotado(client, iniciar_sesion, datos, cuerpo):
    idr = _manual(datos, ID_JURIDICA, 1, 1)
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    assert client.post(f"/api/control-horas/registros/{idr}/anular", json=cuerpo).status_code == 400
    assert _fila(datos, idr)["estado_registro"] == "VIGENTE"


def test_d2_doble_anulacion_registro_inexistente_y_temporizador_en_curso(client, iniciar_sesion, datos):
    idr = _manual(datos, ID_JURIDICA, 1, 1)
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    assert client.post(f"/api/control-horas/registros/{idr}/anular", json={"motivo": MOTIVO}).status_code == 200
    original = _fila(datos, idr)
    segunda = client.post(f"/api/control-horas/registros/{idr}/anular", json={"motivo": "Otro motivo distinto aquí"})
    assert segunda.status_code == 409
    assert _fila(datos, idr)["motivo_anulacion"] == MOTIVO == original["motivo_anulacion"]
    assert len(_auditoria(datos, "REGISTRO_ANULADO")) == 1
    assert client.post("/api/control-horas/registros/99999/anular", json={"motivo": MOTIVO}).status_code == 404
    client.post("/api/control-horas/iniciar", json={"id_tarea": 1})
    abierto = datos.sql("SELECT id_registro FROM registro_tiempo WHERE hora_fin IS NULL", filas=True)[0]["id_registro"]
    assert client.post(f"/api/control-horas/registros/{abierto}/anular", json={"motivo": MOTIVO}).status_code == 409


def test_d2_el_administrador_puede_anular_un_registro_de_otra_area(client, iniciar_sesion, datos):
    idr = _manual(datos, ID_CONTABLE, 2, 2)  # usuario contable, tarea y cliente del área Contable
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    assert client.post(f"/api/control-horas/registros/{idr}/anular", json={"motivo": MOTIVO}).status_code == 200
    assert _fila(datos, idr)["id_usuario"] == ID_CONTABLE and _fila(datos, idr)["id_tarea"] == 2


def test_d2_anulaciones_simultaneas_del_mismo_registro_solo_aplican_una(iniciar_sesion, client, datos):
    idr = _manual(datos, ID_JURIDICA, 1, 1)
    resultados = []

    def lanzar(i):
        c = flask_app.test_client()
        with c.session_transaction() as s:
            s["usuario_id"], s["rol_id"], s["area_id"] = ID_ADMIN, 1, 3
        resultados.append(c.post(f"/api/control-horas/registros/{idr}/anular", json={"motivo": f"Motivo concurrente número {i}"}).status_code)

    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    hilos = [threading.Thread(target=lanzar, args=(i,)) for i in range(6)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sorted(resultados) == [200] + [409] * 5
    assert len(_auditoria(datos, "REGISTRO_ANULADO")) == 1


def test_d2_totales_historial_y_filtros_excluyen_lo_anulado_y_el_admin_puede_verlo_marcado(client, iniciar_sesion, datos):
    vigente = _manual(datos, ID_JURIDICA, 1, 1, minutos=60, dias_atras=2)
    anulado = _manual(datos, ID_JURIDICA, 1, 1, minutos=120, dias_atras=1)
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    assert client.post(f"/api/control-horas/registros/{anulado}/anular", json={"motivo": MOTIVO}).status_code == 200

    datos_admin = client.get("/api/control-horas/registros").get_json()
    assert [r["id_registro"] for r in datos_admin["registros"]] == [vigente]
    resumen = datos_admin["resumen"]
    assert (resumen["minutos_acumulados"], resumen["monto_acumulado"], resumen["total_registros"]) == (60.0, 30000.0, 1)
    assert resumen["totales_cliente"][0]["minutos"] == 60.0 and resumen["totales_tarea"][0]["minutos"] == 60.0

    con = client.get("/api/control-horas/registros", query_string={"incluir_anulados": 1}).get_json()
    por_id = {r["id_registro"]: r for r in con["registros"]}
    assert set(por_id) == {vigente, anulado}
    assert por_id[anulado]["estado_registro"] == "ANULADO" and por_id[anulado]["motivo_anulacion"] == MOTIVO
    assert por_id[anulado]["anulado_por"] == "Admin Ficticia" and por_id[anulado]["fecha_anulacion"]
    assert con["resumen"]["total_registros"] == 1, "los totales nunca incluyen anulados"

    _sesion(client, iniciar_sesion, ID_JURIDICA, 2, 1)
    propio = client.get("/api/control-horas/registros", query_string={"incluir_anulados": 1}).get_json()
    assert [r["id_registro"] for r in propio["registros"]] == [vigente], "un usuario de área no ve anulados"


def test_d2_informes_y_exportaciones_excluyen_los_anulados_y_cuadran_con_sql(client, iniciar_sesion, datos):
    _manual(datos, ID_JURIDICA, 1, 1, minutos=60, dias_atras=2)
    anulado = _manual(datos, ID_JURIDICA, 1, 1, minutos=120, dias_atras=1)
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    antes = client.get("/api/reportes/cobro-por-cliente", query_string={"id_cliente": 1}).get_json()["totales"]["monto"]
    assert antes == 90000.0
    client.post(f"/api/control-horas/registros/{anulado}/anular", json={"motivo": MOTIVO})

    esperado = float(datos.sql("SELECT SUM(monto) m FROM registro_tiempo WHERE estado_registro = 'VIGENTE'", filas=True)[0]["m"])
    assert esperado == 30000.0
    cobro = client.get("/api/reportes/cobro-por-cliente", query_string={"id_cliente": 1}).get_json()
    assert cobro["totales"]["monto"] == esperado
    for agrupar in ("cliente", "tarea", "usuario"):
        horas = client.get("/api/reportes/horas-trabajadas", query_string={"agrupar_por": agrupar})
        assert horas.status_code == 200
        assert horas.get_json()["totales"]["monto"] == esperado, agrupar
        assert horas.get_json()["totales"]["registros"] == 1

    horas = client.get("/api/reportes/horas-trabajadas", query_string={"agrupar_por": "cliente"}).get_json()
    excel = client.get(f"/api/reportes/{horas['id_reporte']}/excel")
    assert excel.status_code == 200
    libro = load_workbook(io.BytesIO(excel.data), data_only=True)
    texto = " ".join(str(c.value) for hoja in libro for fila in hoja.iter_rows() for c in fila if c.value is not None)
    numeros = {float(c.value) for hoja in libro for fila in hoja.iter_rows() for c in fila
               if isinstance(c.value, (int, float)) and not isinstance(c.value, bool)}
    assert 30000.0 in numeros, "el registro vigente aparece valorizado"
    assert not numeros & {60000.0, 90000.0}, "el monto del registro anulado (60.000) y el total antiguo (90.000) no aparecen"
    assert texto
    assert client.get(f"/api/reportes/{horas['id_reporte']}/pdf").status_code == 200


def test_d2_la_auditoria_conserva_el_original_y_el_historial_global_muestra_la_anulacion(client, iniciar_sesion, datos):
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    client.post("/api/control-horas/iniciar", json={"id_tarea": 1})
    _retroceder_abierto(datos, 45)
    client.post("/api/control-horas/detener")
    idr = datos.sql("SELECT id_registro FROM registro_tiempo", filas=True)[0]["id_registro"]
    client.post(f"/api/control-horas/registros/{idr}/anular", json={"motivo": MOTIVO})

    eventos = _auditoria(datos, "REGISTRO_ANULADO")
    assert len(eventos) == 1
    e = eventos[0]
    assert (e["id_usuario"], e["tabla_afectada"], e["id_registro"]) == (ID_ADMIN, "registro_tiempo", idr)
    assert "duracion_minutos=45" in e["datos_anteriores"] and "monto=22500" in e["datos_anteriores"]
    assert "estado_registro=ANULADO" in e["datos_nuevos"] and MOTIVO in e["datos_nuevos"]
    # los eventos originales no se tocan
    assert len(_auditoria(datos, "TEMPORIZADOR_INICIADO")) == 1 and len(_auditoria(datos, "TEMPORIZADOR_DETENIDO")) == 1
    historial = client.get("/api/historial", query_string={"modulo": "Control de horas"}).get_json()
    assert "REGISTRO_ANULADO" in str(historial), "el historial global muestra la anulación"


def test_d2_anular_libera_el_horario_y_conserva_relaciones_con_tarea_y_cliente(client, iniciar_sesion, datos):
    idr = _manual(datos, ID_ADMIN, 1, 1, minutos=60, dias_atras=1, hora="09:00:00")
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    cuerpo = {"id_tarea": 1, "fecha": None, "hora_inicio": "09:00", "hora_fin": "10:00", "observacion": "Mismo horario otra vez"}
    fecha = datos.sql("SELECT DATE_FORMAT(fecha, '%Y-%m-%d') f FROM registro_tiempo WHERE id_registro = %s", (idr,), filas=True)[0]["f"]
    cuerpo["fecha"] = fecha
    assert client.post("/api/control-horas/registros-manuales", json=cuerpo).status_code == 409  # solapa con el vigente
    client.post(f"/api/control-horas/registros/{idr}/anular", json={"motivo": MOTIVO})
    assert client.post("/api/control-horas/registros-manuales", json=cuerpo).status_code == 201  # horario liberado
    fila = _fila(datos, idr)
    assert datos.sql("SELECT titulo FROM tarea WHERE id_tarea = %s", (fila["id_tarea"],), filas=True)
    assert datos.sql("SELECT razon_social FROM cliente WHERE id_cliente = %s", (fila["id_cliente"],), filas=True)


def test_d2_la_migracion_013_es_reversible_y_conserva_los_datos(datos):
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "migraciones",
                        "013_registro_tiempo_anulacion.sql")
    texto = open(ruta, encoding="utf-8").read()
    rollback = re.findall(r"^-- (ALTER TABLE registro_tiempo [^;]+;)", texto, re.M)
    assert len(rollback) == 5
    idr = _manual(datos, ID_JURIDICA, 1, 1, minutos=60)
    for sentencia in rollback:
        datos.sql(sentencia)
    columnas = {c["COLUMN_NAME"] for c in datos.sql(
        "SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'registro_tiempo'",
        filas=True)}
    assert not columnas & {"estado_registro", "anulado_por", "fecha_anulacion", "motivo_anulacion"}
    assert float(datos.sql("SELECT monto FROM registro_tiempo WHERE id_registro = %s", (idr,), filas=True)[0]["monto"]) == 30000.0
    # y se puede volver a aplicar
    for sentencia in [s.strip() for s in re.sub(r"^--.*$", "", texto, flags=re.M).split(";") if s.strip()]:
        datos.sql(sentencia)
    assert _fila(datos, idr)["estado_registro"] == "VIGENTE"


def test_d3_el_sistema_no_guarda_si_un_registro_fue_facturado(datos):
    """Limitación documentada (06, D3): no existe ningún dato de facturación en el esquema, por eso la anulación
    NO bloquea por «facturado». Si algún día se agrega, esta prueba falla y obliga a revisar el bloqueo."""
    columnas = datos.sql(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = DATABASE() "
        "AND column_name LIKE '%%factur%%'",
        filas=True)
    assert columnas == []
    # La tabla `cobro` existe pero ninguna ruta la lee ni la escribe: no es evidencia de facturación.
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for carpeta, _, archivos in os.walk(os.path.join(raiz, "backend")):
        for a in archivos:
            if a.endswith(".py"):
                codigo = open(os.path.join(carpeta, a), encoding="utf-8").read()
                assert not re.search(r"(FROM|INTO|UPDATE|JOIN)\s+cobro\b", codigo), a


# ============================================ D6 · mensaje claro (la regla NO cambia)
@pytest.mark.parametrize("estado,fragmento", [("COMPLETADA", "completada"), ("CANCELADA", "cancelada")])
def test_d6_una_tarea_cerrada_sigue_rechazando_horas_pero_explica_por_que(client, iniciar_sesion, datos, estado, fragmento):
    datos.sql("UPDATE tarea SET estado = %s WHERE id_tarea = 1", (estado,))
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    r = client.post("/api/control-horas/iniciar", json={"id_tarea": 1})
    assert r.status_code == 404 and fragmento in r.get_json()["error"]
    manual = client.post("/api/control-horas/registros-manuales", json={
        "id_tarea": 1, "fecha": "2026-11-01", "hora_inicio": "09:00", "hora_fin": "10:00", "observacion": "Trabajo ficticio"})
    assert manual.status_code == 404 and fragmento in manual.get_json()["error"]
    assert datos.sql("SELECT COUNT(*) n FROM registro_tiempo", filas=True)[0]["n"] == 0, "la regla de negocio no cambió"


def test_d6_un_usuario_de_area_no_averigua_el_estado_de_tareas_ajenas(client, iniciar_sesion, datos):
    datos.sql("UPDATE tarea SET estado = 'COMPLETADA' WHERE id_tarea = 2")  # tarea del usuario contable
    _sesion(client, iniciar_sesion, ID_JURIDICA, 2, 1)
    r = client.post("/api/control-horas/iniciar", json={"id_tarea": 2})
    assert r.status_code == 404 and r.get_json()["error"] == "La tarea no existe o no está disponible para este usuario."
    r = client.post("/api/control-horas/iniciar", json={"id_tarea": 9999})
    assert r.get_json()["error"] == "La tarea no existe o no está disponible para este usuario."


def test_d6_un_cliente_inactivo_se_explica(client, iniciar_sesion, datos):
    datos.sql("UPDATE cliente SET estado = 'INACTIVO' WHERE id_cliente = 1")
    _sesion(client, iniciar_sesion, ID_ADMIN, 1, 3)
    r = client.post("/api/control-horas/iniciar", json={"id_tarea": 1})
    assert r.status_code == 404 and "inactivo" in r.get_json()["error"]
