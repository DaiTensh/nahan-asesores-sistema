# -*- coding: utf-8 -*-
"""SEC-02 — Límite de intentos fallidos de inicio de sesión.

Cada intento reserva una fila en `intento_login_fallido` antes de comprobar la
contraseña; la fila se conserva si el intento falla y se borra si tiene éxito.
Tres contadores en una ventana móvil de 15 minutos: cuenta + IP (5), cuenta
(15) e IP (40). Al alcanzar un umbral: 429 con Retry-After, sin escribir nada.

Corre sobre SQLite en memoria con las rutas reales y el arnés de RF30. SQLite
no tiene bloqueos con nombre reales ni el aislamiento de InnoDB: aquí se
verifican las reglas, la ventana, el orden de las sentencias, los errores y la
privacidad. La competencia entre solicitudes simultáneas y la equivalencia de
correos con el collation se comprueban contra MySQL real (fuera de la suite).
"""
import ipaddress
import json
import logging

import mysql.connector.errors as errores_mysql
import pytest

import backend.routes.auth_routes as auth_routes
import backend.utils.limitador_login as limitador
from backend.app import create_app
from tests.test_rf30_historial_accesos import (  # noqa: F401  (fixtures y ayudas del arnés RF30)
    CLAVE,
    _eventos,
    base,
    cliente,
)

IP_A = "203.0.113.10"
IP_B = "203.0.113.11"
IP_C = "203.0.113.12"
IP_D = "203.0.113.13"
ADMIN = "admin@nahan.local"
JURIDICA = "juridica@nahan.local"
INACTIVA = "contable@nahan.local"  # cuenta inactiva en el arnés RF30
INCORRECTA = "clave-equivocada-xyz"
BLOQUEO = "nahan:login:reserva"


@pytest.fixture(autouse=True)
def verificaciones(monkeypatch):
    """bcrypt real cuesta ~235 ms por intento. Se sustituye por una
    comparación con CLAVE y se anota cuántas veces se verificó una contraseña."""
    llamadas = []

    def comprobar(password, password_hash):
        llamadas.append(password)
        return password == CLAVE

    monkeypatch.setattr(auth_routes, "check_password", comprobar)
    return llamadas


def _intentar(cliente, email=ADMIN, clave=INCORRECTA, ip=IP_A, **extra):
    return cliente.post(
        "/api/login",
        json={"email": email, "password": clave},
        environ_overrides={"REMOTE_ADDR": ip},
        **extra,
    )


def _fallar(cliente, veces, email=ADMIN, ip=IP_A):
    return [_intentar(cliente, email, INCORRECTA, ip).status_code for _ in range(veces)]


def _filas(base):
    return [dict(f) for f in base.execute(
        "SELECT * FROM intento_login_fallido ORDER BY id_intento").fetchall()]


def _cuantas(base):
    return base.execute("SELECT COUNT(*) FROM intento_login_fallido").fetchone()[0]


def _envejecer(base, minutos):
    base.execute("UPDATE intento_login_fallido SET fecha = datetime(fecha, ?)", (f"-{minutos} minutes",))
    base.commit()


def _error_mysql(errno):
    return lambda: errores_mysql.DatabaseError("detalle-interno persona@secreta.cl", errno=errno)


def _sin_sesion(cliente):
    with cliente.session_transaction() as sesion:
        assert "usuario_id" not in sesion


# --- Constantes aprobadas ----------------------------------------------------------

def test_umbrales_y_ventana_aprobados():
    assert limitador.VENTANA_MINUTOS == 15
    assert (limitador.MAX_POR_PAR, limitador.MAX_POR_CUENTA, limitador.MAX_POR_IP) == (5, 15, 40)
    assert limitador.RETENCION_HORAS == 24
    assert limitador.LOTE_PURGA == 500


# --- Cuenta + IP: cinco fallos permitidos, el sexto bloqueado ----------------------------

def test_cinco_fallos_se_permiten_y_el_sexto_se_bloquea(cliente, base, verificaciones):
    codigos = _fallar(cliente, 6)

    assert codigos == [401, 401, 401, 401, 401, 429]
    assert len(verificaciones) == 5, "el sexto intento ni siquiera verifica la contraseña"
    assert _cuantas(base) == 5


def test_con_contrasena_correcta_el_bloqueo_tambien_aplica(cliente, base, verificaciones):
    _fallar(cliente, 5)

    respuesta = _intentar(cliente, ADMIN, CLAVE)

    assert respuesta.status_code == 429
    assert CLAVE not in verificaciones
    _sin_sesion(cliente)
    assert _eventos(base) == []


def test_el_bloqueo_de_un_par_no_afecta_a_otra_ip_ni_a_otra_cuenta(cliente):
    _fallar(cliente, 5, ADMIN, IP_A)
    assert _intentar(cliente, ADMIN, INCORRECTA, IP_A).status_code == 429

    assert _intentar(cliente, ADMIN, INCORRECTA, IP_B).status_code == 401, "misma cuenta, otra IP"
    assert _intentar(cliente, JURIDICA, INCORRECTA, IP_A).status_code == 401, "misma IP, otra cuenta"
    assert _intentar(cliente, JURIDICA, CLAVE, IP_A).status_code == 200


# --- Cuenta: ataque distribuido ----------------------------------------------------------

def test_quince_fallos_desde_varias_ip_bloquean_la_cuenta(cliente, base):
    for ip in (IP_A, IP_B, IP_C):
        assert _fallar(cliente, 5, ADMIN, ip) == [401] * 5

    respuesta = _intentar(cliente, ADMIN, INCORRECTA, IP_D)

    assert respuesta.status_code == 429
    assert _cuantas(base) == 15, "el intento rechazado no consume cuota"


def test_el_bloqueo_de_cuenta_no_afecta_a_otras_cuentas(cliente):
    for ip in (IP_A, IP_B, IP_C):
        _fallar(cliente, 5, ADMIN, ip)

    assert _intentar(cliente, JURIDICA, CLAVE, IP_D).status_code == 200


# --- IP: una IP contra muchas cuentas -------------------------------------------------------

def test_cuarenta_fallos_desde_una_ip_bloquean_a_esa_ip(cliente, base):
    codigos = [_intentar(cliente, f"nadie{i}@nahan.local", INCORRECTA, IP_A).status_code for i in range(40)]
    assert codigos == [401] * 40

    assert _intentar(cliente, "otro@nahan.local", INCORRECTA, IP_A).status_code == 429
    assert _intentar(cliente, JURIDICA, CLAVE, IP_A).status_code == 429
    assert _cuantas(base) == 40
    assert _intentar(cliente, JURIDICA, CLAVE, IP_B).status_code == 200, "otra IP no se ve afectada"


def test_usuarios_legitimos_que_comparten_ip_no_se_bloquean_entre_si(cliente):
    cuentas = [ADMIN, JURIDICA] + [f"colega{i}@nahan.local" for i in range(6)]
    for email in cuentas:
        assert _fallar(cliente, 3, email, IP_A) == [401] * 3  # 24 fallos, ninguna cuenta pasa de 3

    assert _intentar(cliente, ADMIN, CLAVE, IP_A).status_code == 200
    assert _intentar(cliente, JURIDICA, CLAVE, IP_A).status_code == 200


# --- Cuentas inexistentes e inactivas: sin enumeración ------------------------------------------------

def test_una_cuenta_inexistente_se_limita_igual_que_una_existente(cliente):
    inexistente = [_intentar(cliente, "fantasma@nahan.local", INCORRECTA).status_code for _ in range(6)]
    existente = _fallar(cliente, 6, ADMIN, IP_B)

    assert inexistente == existente == [401, 401, 401, 401, 401, 429]


def test_el_429_es_identico_para_cuentas_existentes_inexistentes_e_inactivas(cliente):
    _fallar(cliente, 5, ADMIN, IP_A)
    _fallar(cliente, 5, "fantasma@nahan.local", IP_A)
    for _ in range(5):
        _intentar(cliente, INACTIVA, INCORRECTA, IP_A)

    cuerpos = []
    for email in (ADMIN, "fantasma@nahan.local", INACTIVA):
        respuesta = _intentar(cliente, email, INCORRECTA, IP_A)
        assert respuesta.status_code == 429
        cuerpos.append(respuesta.get_json())

    assert cuerpos[0].keys() == cuerpos[1].keys() == cuerpos[2].keys()
    assert {c["error"] for c in cuerpos} == {limitador.MENSAJE_LIMITE}
    assert {c["codigo"] for c in cuerpos} == {"DEMASIADOS_INTENTOS"}


def test_una_cuenta_inactiva_conserva_el_403_hasta_alcanzar_el_limite(cliente, base):
    codigos = [_intentar(cliente, INACTIVA, CLAVE).status_code for _ in range(6)]

    assert codigos == [403, 403, 403, 403, 403, 429]
    assert _cuantas(base) == 5


def test_las_respuestas_anteriores_al_limite_no_cambian(cliente):
    inexistente = _intentar(cliente, "fantasma@nahan.local", INCORRECTA)
    mala_clave = _intentar(cliente, ADMIN, INCORRECTA, IP_B)

    assert inexistente.status_code == mala_clave.status_code == 401
    assert inexistente.get_json() == mala_clave.get_json() == {"error": "Credenciales incorrectas"}
    assert _intentar(cliente, INACTIVA, CLAVE, IP_C).get_json() == {
        "error": "Usuario inactivo. Contacte al administrador."}


# --- Variantes del mismo correo comparten la clave ---------------------------------------------------------

def test_variantes_de_un_mismo_correo_comparten_cuota(cliente):
    variantes = ["Persona@Nahan.local", "persona@nahan.local ", "PERSONA@NAHAN.LOCAL",
                 "persona@nahan.local   ", "Persona@nahan.local"]
    assert [_intentar(cliente, v).status_code for v in variantes] == [401] * 5

    assert _intentar(cliente, "persona@nahan.local").status_code == 429


# --- Login exitoso ------------------------------------------------------------------------------------

def test_un_login_exitoso_borra_solo_su_reserva(cliente, base):
    _fallar(cliente, 4, ADMIN, IP_A)

    respuesta = _intentar(cliente, ADMIN, CLAVE, IP_A)

    assert respuesta.status_code == 200
    assert _cuantas(base) == 4, "los 4 fallos siguen; la reserva del éxito se borró"
    with cliente.session_transaction() as sesion:
        assert sesion["usuario_id"] == 1


def test_un_login_exitoso_sin_fallos_no_deja_filas(cliente, base):
    assert _intentar(cliente, JURIDICA, CLAVE).status_code == 200
    assert _cuantas(base) == 0


def test_los_exitos_no_consumen_cuota(cliente, base):
    for _ in range(20):
        assert _intentar(cliente, JURIDICA, CLAVE, IP_A).status_code == 200
    assert _cuantas(base) == 0
    assert _fallar(cliente, 5, JURIDICA, IP_A) == [401] * 5


# --- Ventana de 15 minutos ------------------------------------------------------------------------------

def test_dentro_de_los_15_minutos_el_bloqueo_sigue(cliente, base):
    _fallar(cliente, 5)
    _envejecer(base, 14)

    assert _intentar(cliente).status_code == 429


def test_pasados_los_15_minutos_la_cuota_se_libera(cliente, base):
    _fallar(cliente, 5)
    _envejecer(base, 16)

    assert _intentar(cliente, ADMIN, CLAVE).status_code == 200


def test_la_ventana_es_movil(cliente, base):
    _fallar(cliente, 3)
    _envejecer(base, 10)
    _fallar(cliente, 2)          # ahora hay 3 de hace 10 min y 2 recientes: 5 en la ventana
    assert _intentar(cliente).status_code == 429

    _envejecer(base, 6)          # los 3 primeros llevan 16 min; los 2 últimos, 6
    assert _intentar(cliente).status_code == 401
    assert _cuantas(base) == 6


def test_los_intentos_rechazados_no_alargan_el_bloqueo(cliente, base):
    _fallar(cliente, 5)
    for _ in range(30):
        assert _intentar(cliente).status_code == 429
    _envejecer(base, 16)

    assert _intentar(cliente, ADMIN, CLAVE).status_code == 200


# --- Retry-After ---------------------------------------------------------------------------------------------

def test_retry_after_coincide_con_el_cuerpo_y_esta_en_rango(cliente):
    _fallar(cliente, 5)

    respuesta = _intentar(cliente)

    assert respuesta.status_code == 429
    cuerpo = respuesta.get_json()
    assert cuerpo["error"] == "Demasiados intentos fallidos. Espere unos minutos e inténtelo de nuevo."
    assert cuerpo["codigo"] == "DEMASIADOS_INTENTOS"
    assert set(cuerpo) == {"error", "codigo", "reintentar_en_segundos"}
    assert respuesta.headers["Retry-After"] == str(cuerpo["reintentar_en_segundos"])
    assert 880 <= cuerpo["reintentar_en_segundos"] <= 900


def test_retry_after_disminuye_con_el_tiempo(cliente, base):
    _fallar(cliente, 5)
    _envejecer(base, 10)

    segundos = _intentar(cliente).get_json()["reintentar_en_segundos"]

    assert 280 <= segundos <= 300


def test_retry_after_espera_hasta_que_el_contador_baje_del_umbral(cliente, base):
    _fallar(cliente, 2)
    _envejecer(base, 10)
    _fallar(cliente, 3)   # 2 de hace 10 min y 3 recientes

    segundos = _intentar(cliente).get_json()["reintentar_en_segundos"]

    assert 280 <= segundos <= 300, "basta con que expire el más antiguo"


def test_el_429_no_revela_que_contador_lo_produjo(cliente):
    for ip in (IP_A, IP_B, IP_C):
        _fallar(cliente, 5, ADMIN, ip)
    por_cuenta = _intentar(cliente, ADMIN, INCORRECTA, IP_D).get_json()
    _fallar(cliente, 5, JURIDICA, IP_A)
    por_par = _intentar(cliente, JURIDICA, INCORRECTA, IP_A).get_json()

    assert por_cuenta.keys() == por_par.keys()
    assert por_cuenta["error"] == por_par["error"]
    assert por_cuenta["codigo"] == por_par["codigo"]


# --- Los rechazados no escriben ni consumen --------------------------------------------------------------------

def test_un_intento_rechazado_no_escribe_en_la_base_ni_toma_bloqueos(cliente, base, verificaciones):
    _fallar(cliente, 5)
    antes = _filas(base)
    base.bitacora.clear()
    verificaciones.clear()

    for _ in range(10):
        assert _intentar(cliente).status_code == 429

    assert _filas(base) == antes
    assert verificaciones == []
    assert not any(s.startswith(("INSERT", "DELETE", "UPDATE")) or "GET_LOCK" in s for s in base.bitacora)
    assert base.bloqueos == {}


# --- Orden de las sentencias y garantías de concurrencia ----------------------------------------------------------

def test_la_reserva_sigue_el_orden_que_garantiza_la_concurrencia(cliente, base, monkeypatch):
    momentos = {}

    def comprobar(password, password_hash):
        momentos["bitacora"] = list(base.bitacora)
        momentos["bloqueos"] = dict(base.bloqueos)
        return False

    monkeypatch.setattr(auth_routes, "check_password", comprobar)
    base.bitacora.clear()

    assert _intentar(cliente).status_code == 401

    previas = momentos["bitacora"]

    def posicion(texto, desde=0):
        for i in range(desde, len(previas)):
            if texto in previas[i]:
                return i
        raise AssertionError(f"{texto!r} no aparece en {previas}")

    usuario = posicion("FROM usuario u")
    prechequeo = posicion("SELECT (SELECT COUNT(*)", usuario)
    tomar = posicion("GET_LOCK", prechequeo)
    assert previas[tomar - 1] == "ROLLBACK", "las lecturas previas no retienen bloqueos mientras se espera"
    revertir = tomar + 1
    assert previas[revertir] == "ROLLBACK", "tras tomar el bloqueo se termina la instantánea anterior"
    recuento = posicion("SELECT (SELECT COUNT(*)", revertir)
    insertar = posicion("INSERT INTO intento_login_fallido", recuento)
    confirmar = insertar + 1
    assert previas[confirmar] == "COMMIT", "la reserva se confirma antes de soltar el bloqueo"
    soltar = posicion("RELEASE_LOCK", confirmar)
    assert previas[-1] == "ROLLBACK", "sin transacción abierta mientras se verifica la contraseña"
    assert soltar < len(previas) - 1
    assert momentos["bloqueos"] == {}, "bcrypt se ejecuta sin ningún bloqueo con nombre tomado"
    assert previas.count("COMMIT") == 1
    assert "nahan:login:reserva" not in base.bloqueos


def test_el_bloqueo_se_toma_con_el_nombre_y_el_tiempo_previstos(cliente, monkeypatch):
    pedidos = []
    original = limitador._adquirir_bloqueo

    def espiar(cursor, nombre, segundos):
        pedidos.append((nombre, segundos))
        return original(cursor, nombre, segundos)

    monkeypatch.setattr(limitador, "_adquirir_bloqueo", espiar)

    _intentar(cliente)

    assert pedidos == [(BLOQUEO, 2)]
    assert limitador.NOMBRE_BLOQUEO_RESERVA == BLOQUEO and limitador.SEGUNDOS_ESPERA_BLOQUEO == 2


def test_el_exito_borra_la_reserva_antes_de_auditar_y_en_la_misma_transaccion(cliente, base):
    base.bitacora.clear()

    assert _intentar(cliente, JURIDICA, CLAVE).status_code == 200

    sentencias = base.bitacora
    borrar = next(i for i, s in enumerate(sentencias) if s.startswith("DELETE FROM intento_login_fallido"))
    auditar = next(i for i, s in enumerate(sentencias) if "INSERT INTO auditoria" in s)
    confirmar = max(i for i, s in enumerate(sentencias) if s == "COMMIT")
    assert borrar < auditar < confirmar
    assert sentencias[borrar - 1] != "COMMIT", "el DELETE no va en una transacción aparte"
    assert sentencias.count("COMMIT") == 2, "reserva y login/auditoría son dos transacciones"
    assert base.bloqueos == {}


def test_la_sesion_solo_se_crea_si_la_transaccion_del_login_se_completa(cliente, base):
    base.inyectar_fallo("INSERT INTO auditoria", lambda: RuntimeError("falla"), 1)

    respuesta = _intentar(cliente, JURIDICA, CLAVE)

    assert respuesta.status_code == 500
    _sin_sesion(cliente)
    assert _eventos(base) == []
    assert _cuantas(base) == 1, "la reserva se conserva si el login no se completa (lado seguro)"


def test_ninguna_ruta_deja_bloqueos_tomados(cliente, base):
    _fallar(cliente, 6)
    _intentar(cliente, JURIDICA, CLAVE)
    _intentar(cliente, INACTIVA, CLAVE)
    _intentar(cliente, "fantasma@nahan.local")

    assert base.bloqueos == {}


# --- Errores: política aprobada -------------------------------------------------------------------------------------

def _comprobar_503(respuesta, cliente, verificaciones, segundos="5"):
    assert respuesta.status_code == 503
    assert respuesta.headers["Retry-After"] == segundos
    cuerpo = respuesta.get_json()
    assert cuerpo == {"error": limitador.MENSAJE_NO_DISPONIBLE, "codigo": "SERVICIO_NO_DISPONIBLE"}
    assert verificaciones == [], "sin conocer el estado de los contadores no se verifica la contraseña"
    _sin_sesion(cliente)


@pytest.mark.parametrize("errno", [1146, 1054, 1366, 1265, 1406])
def test_tabla_inexistente_o_migracion_incompleta_responde_503_y_registra_critico(
        cliente, base, verificaciones, caplog, errno):
    base.inyectar_fallo("SELECT (SELECT COUNT(*)", _error_mysql(errno), 1)

    with caplog.at_level(logging.DEBUG):
        respuesta = _intentar(cliente, JURIDICA, CLAVE)

    _comprobar_503(respuesta, cliente, verificaciones)
    criticos = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(criticos) == 1
    assert "migración 008" in criticos[0].getMessage()
    assert str(errno) in criticos[0].getMessage()
    assert "persona@secreta.cl" not in caplog.text, "no se registra el texto del error de MySQL"


def test_la_tabla_inexistente_tambien_se_detecta_al_reservar(cliente, base, verificaciones):
    base.inyectar_fallo("INSERT INTO intento_login_fallido", _error_mysql(1146), 2)

    respuesta = _intentar(cliente, JURIDICA, CLAVE)

    _comprobar_503(respuesta, cliente, verificaciones)
    assert base.bloqueos == {}
    assert _cuantas(base) == 0


def test_el_error_del_servidor_no_desactiva_en_silencio_la_proteccion(cliente, base, verificaciones):
    """Mientras el limitador falla, ni siquiera el usuario correcto entra."""
    base.inyectar_fallo("SELECT (SELECT COUNT(*)", _error_mysql(1146), 5)

    for _ in range(5):
        assert _intentar(cliente, JURIDICA, CLAVE).status_code == 503
    assert verificaciones == []
    _sin_sesion(cliente)


def test_timeout_de_get_lock_responde_503_sin_reservar(cliente, base, verificaciones):
    base.bloqueos[BLOQUEO] = "ajeno"

    respuesta = _intentar(cliente, JURIDICA, CLAVE)

    _comprobar_503(respuesta, cliente, verificaciones, segundos="2")
    assert _cuantas(base) == 0
    assert base.bloqueos == {BLOQUEO: "ajeno"}, "no se toca un bloqueo ajeno"


@pytest.mark.parametrize("errno", [2006, 2013, 1317, 1053])
def test_error_transitorio_responde_503_sin_reintento(cliente, base, verificaciones, caplog, errno):
    base.inyectar_fallo("INSERT INTO intento_login_fallido", _error_mysql(errno), 5)
    base.bitacora.clear()

    with caplog.at_level(logging.DEBUG):
        respuesta = _intentar(cliente, JURIDICA, CLAVE)

    _comprobar_503(respuesta, cliente, verificaciones)
    assert sum("INSERT INTO intento_login_fallido" in s for s in base.bitacora) == 1
    assert [r.levelno for r in caplog.records if "Limitador" in r.getMessage()] == [logging.ERROR]
    assert base.bloqueos == {}


@pytest.mark.parametrize("errno", [1213, 1205])
def test_deadlock_o_timeout_de_fila_se_reintenta_una_vez(cliente, base, verificaciones, errno):
    base.inyectar_fallo("INSERT INTO intento_login_fallido", _error_mysql(errno), 1)
    base.bitacora.clear()

    respuesta = _intentar(cliente, JURIDICA, INCORRECTA)

    assert respuesta.status_code == 401, "el reintento tuvo éxito y el intento siguió su curso"
    assert _cuantas(base) == 1, "una sola reserva: nada se duplica"
    assert sum("GET_LOCK" in s for s in base.bitacora) == 2
    assert sum("RELEASE_LOCK" in s for s in base.bitacora) == 2
    assert base.bloqueos == {}
    assert len(verificaciones) == 1


@pytest.mark.parametrize("errno", [1213, 1205])
def test_si_el_reintento_tambien_falla_responde_503(cliente, base, verificaciones, errno):
    base.inyectar_fallo("INSERT INTO intento_login_fallido", _error_mysql(errno), 2)
    base.bitacora.clear()

    respuesta = _intentar(cliente, JURIDICA, CLAVE)

    _comprobar_503(respuesta, cliente, verificaciones)
    assert sum("INSERT INTO intento_login_fallido" in s for s in base.bitacora) == 2, "un solo reintento"
    assert _cuantas(base) == 0
    assert base.bloqueos == {}


def test_deadlock_en_el_recuento_de_la_seccion_tambien_se_reintenta(cliente, base, monkeypatch):
    monkeypatch.setattr(auth_routes, "verificar_cupo", lambda cursor, clave, ip: None)  # sin prechequeo
    base.inyectar_fallo("SELECT (SELECT COUNT(*)", _error_mysql(1213), 1)
    base.bitacora.clear()

    assert _intentar(cliente, JURIDICA, CLAVE).status_code == 200

    assert sum("GET_LOCK" in s for s in base.bitacora) == 2
    assert base.bloqueos == {}
    assert _cuantas(base) == 0


def test_el_prechequeo_no_se_reintenta(cliente, base, verificaciones):
    base.inyectar_fallo("SELECT (SELECT COUNT(*)", _error_mysql(1213), 1)

    respuesta = _intentar(cliente, JURIDICA, CLAVE)

    _comprobar_503(respuesta, cliente, verificaciones)


def test_un_error_inesperado_responde_500_generico_sin_sesion(cliente, base, monkeypatch, verificaciones):
    def fallar(*args, **kwargs):
        raise RuntimeError("error de programación")

    monkeypatch.setattr(auth_routes, "reservar_intento", fallar)

    respuesta = _intentar(cliente, JURIDICA, CLAVE)

    assert respuesta.status_code == 500
    assert respuesta.get_json() == {"error": "Error interno al iniciar sesión"}
    assert verificaciones == []
    _sin_sesion(cliente)


def test_mysql_inaccesible_conserva_el_fallo_actual(cliente, monkeypatch, verificaciones):
    monkeypatch.setattr(auth_routes, "get_connection", lambda: None)

    respuesta = _intentar(cliente, JURIDICA, CLAVE)

    assert respuesta.status_code == 500
    assert respuesta.get_json() == {"error": "Error interno al iniciar sesión"}
    assert verificaciones == []


def test_un_fallo_al_soltar_el_bloqueo_no_impide_el_login(cliente, base, caplog):
    base.inyectar_fallo("RELEASE_LOCK", _error_mysql(2013), 1)

    with caplog.at_level(logging.DEBUG):
        respuesta = _intentar(cliente, JURIDICA, CLAVE)

    assert respuesta.status_code == 200
    assert "no se pudo liberar el bloqueo" in caplog.text


# --- Purga ----------------------------------------------------------------------------------------------------------

def _sembrar_antiguas(base, desde, hasta, horas=30):
    base.executemany(
        "INSERT INTO intento_login_fallido (id_intento, clave_cuenta, ip_cliente, id_usuario, fecha) "
        "VALUES (?, ?, NULL, NULL, datetime('now', ?))",
        [(i, b"\x00" * 32, f"-{horas} hours") for i in range(desde, hasta + 1)],
    )
    base.commit()


def test_la_purga_borra_un_lote_acotado_de_filas_vencidas(cliente, base):
    _sembrar_antiguas(base, 1, 699)
    assert _fallar(cliente, 1) == [401]       # recibe el id 700: toca purgar

    vencidas = base.execute(
        "SELECT COUNT(*) FROM intento_login_fallido WHERE fecha < datetime('now', '-24 hours')").fetchone()[0]
    assert vencidas == 699 - limitador.LOTE_PURGA
    assert base.execute("SELECT MIN(id_intento) FROM intento_login_fallido").fetchone()[0] == 501, \
        "se borran las más antiguas primero"
    assert base.bloqueos == {}


def test_la_purga_conserva_las_filas_recientes(cliente, base):
    _sembrar_antiguas(base, 90, 98, horas=2)
    _sembrar_antiguas(base, 99, 99, horas=30)

    assert _fallar(cliente, 1) == [401]       # id 100

    ids = [f["id_intento"] for f in _filas(base)]
    assert 99 not in ids
    assert ids == list(range(90, 99)) + [100]


def test_la_purga_no_ocurre_en_cada_solicitud(cliente, base):
    _sembrar_antiguas(base, 1, 40)

    assert _fallar(cliente, 3) == [401] * 3   # ids 41, 42, 43

    assert _cuantas(base) == 43, "no es id múltiplo de 100: no se purga"


def test_un_error_de_purga_es_solo_una_advertencia(cliente, base, caplog):
    _sembrar_antiguas(base, 99, 99)
    base.inyectar_fallo("DELETE FROM intento_login_fallido WHERE id_intento IN", _error_mysql(1205), 1)

    with caplog.at_level(logging.DEBUG):
        respuesta = _intentar(cliente, JURIDICA, CLAVE)   # id 100: toca purgar

    assert respuesta.status_code == 200
    assert "no se pudo purgar" in caplog.text
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
    assert base.bloqueos == {}


def test_si_otro_worker_purga_no_se_espera(cliente, base):
    _sembrar_antiguas(base, 99, 99)
    base.bloqueos["nahan:login:purga"] = "ajeno"

    assert _fallar(cliente, 1) == [401]

    assert _cuantas(base) == 2, "la purga se omite sin esperar ni fallar"


# --- Direcciones IP ---------------------------------------------------------------------------------------------------

def test_ipv4_se_guarda_en_cuatro_bytes(cliente, base):
    _intentar(cliente, ip="198.51.100.77")

    assert _filas(base)[0]["ip_cliente"] == ipaddress.ip_address("198.51.100.77").packed


def test_ipv6_se_agrupa_por_prefijo_64(cliente, base):
    mismas = ["2001:db8:aaaa:1::1", "2001:db8:aaaa:1:ffff:ffff:ffff:ffff", "2001:DB8:AAAA:1:0:0:0:7",
              "2001:db8:aaaa:1::2", "2001:db8:aaaa:1::3"]
    assert [_intentar(cliente, ip=ip).status_code for ip in mismas] == [401] * 5

    assert _intentar(cliente, ip="2001:db8:aaaa:1::99").status_code == 429, "mismo /64: mismo cupo"
    assert _intentar(cliente, ip="2001:db8:aaaa:2::1").status_code == 401, "otro /64"
    assert {f["ip_cliente"] for f in _filas(base)[:5]} == {ipaddress.ip_address("2001:db8:aaaa:1::").packed[:8]}


def test_ipv4_mapeada_en_ipv6_equivale_a_ipv4(cliente, base):
    _intentar(cliente, ip="::ffff:203.0.113.10")

    assert _filas(base)[0]["ip_cliente"] == ipaddress.ip_address("203.0.113.10").packed


@pytest.mark.parametrize("direccion, esperado", [
    ("203.0.113.5", bytes([203, 0, 113, 5])),
    ("2001:db8::1", bytes.fromhex("20010db800000000")),
    ("::ffff:10.1.2.3", bytes([10, 1, 2, 3])),
    ("fe80::1%eth0", bytes.fromhex("fe80000000000000")),
    ("127.0.0.1", None), ("::1", None), ("0.0.0.0", None), ("::", None),
    ("", None), (None, None), ("no-es-una-ip", None), ("999.1.1.1", None),
])
def test_normalizar_ip(direccion, esperado):
    assert limitador.normalizar_ip(direccion) == esperado


def test_ip_de_loopback_omite_par_e_ip_pero_mantiene_el_limite_por_cuenta(cliente, base, caplog):
    with caplog.at_level(logging.DEBUG):
        codigos = [_intentar(cliente, ADMIN, INCORRECTA, "127.0.0.1").status_code for _ in range(16)]

    assert codigos == [401] * 15 + [429], "5 fallos de una IP loopback no bloquean; 15 por cuenta sí"
    assert {f["ip_cliente"] for f in _filas(base)} == {None}
    avisos = [r.getMessage() for r in caplog.records if "IP de cliente no disponible" in r.getMessage()]
    assert len(avisos) == 16
    assert ADMIN not in caplog.text and INCORRECTA not in caplog.text


def test_loopback_no_bloquea_por_ip_aunque_haya_muchas_cuentas(cliente):
    codigos = [_intentar(cliente, f"nadie{i}@nahan.local", INCORRECTA, "127.0.0.1").status_code
               for i in range(45)]

    assert codigos == [401] * 45


def test_las_cabeceras_enviadas_por_el_cliente_no_cambian_la_ip(cliente, base, monkeypatch):
    monkeypatch.setenv("TRUST_PROXY", "false")
    aplicacion = create_app()
    aplicacion.config["TESTING"] = True

    with aplicacion.test_client() as http:
        http.post("/api/login", json={"email": ADMIN, "password": INCORRECTA},
                  headers={"X-Forwarded-For": "198.51.100.7", "X-Real-IP": "198.51.100.8"},
                  environ_overrides={"REMOTE_ADDR": "203.0.113.5"})

    assert _filas(base)[0]["ip_cliente"] == ipaddress.ip_address("203.0.113.5").packed


def test_con_proxy_de_confianza_solo_cuenta_la_ultima_entrada_de_x_forwarded_for(cliente, base, monkeypatch):
    """Nginx añade la IP real al final: lo que el cliente antepone se ignora."""
    monkeypatch.setenv("TRUST_PROXY", "true")
    aplicacion = create_app()
    aplicacion.config["TESTING"] = True

    with aplicacion.test_client() as http:
        http.post("/api/login", json={"email": ADMIN, "password": INCORRECTA},
                  headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.5"},
                  environ_overrides={"REMOTE_ADDR": "127.0.0.1"})

    assert _filas(base)[0]["ip_cliente"] == ipaddress.ip_address("203.0.113.5").packed


# --- Reinicios y varios workers ----------------------------------------------------------------------------------------

def test_los_contadores_sobreviven_a_un_reinicio_de_la_aplicacion(cliente, base):
    _fallar(cliente, 5)

    reiniciada = create_app()
    reiniciada.config["TESTING"] = True
    with reiniciada.test_client() as http:
        respuesta = http.post("/api/login", json={"email": ADMIN, "password": CLAVE},
                              environ_overrides={"REMOTE_ADDR": IP_A})

    assert respuesta.status_code == 429


def test_dos_aplicaciones_comparten_los_contadores_como_dos_workers(cliente, base):
    otra = create_app()
    otra.config["TESTING"] = True
    with otra.test_client() as http:
        for _ in range(3):
            http.post("/api/login", json={"email": ADMIN, "password": INCORRECTA},
                      environ_overrides={"REMOTE_ADDR": IP_A})
    _fallar(cliente, 2)

    assert _intentar(cliente).status_code == 429


def test_la_clave_de_cuenta_depende_del_secreto_de_la_aplicacion():
    peso = "0E330F640E33"
    uno = limitador.clave_desde_peso(peso, b"a" * 32)
    dos = limitador.clave_desde_peso(peso, b"b" * 32)

    assert len(uno) == 32 and uno != dos
    assert uno == limitador.clave_desde_peso(peso, b"a" * 32)
    assert limitador.clave_desde_peso(peso + "0209" * 3, b"a" * 32) == uno, "los espacios finales no cuentan"


@pytest.mark.parametrize("peso, esperado", [
    ("0E330209", "0E33"), ("0209", ""), ("02090209", ""), ("0E330209", "0E33"),
    ("0E33", "0E33"), ("", ""), ("E0209", "E0209"), ("02090E33", "02090E33"),
])
def test_quitar_relleno(peso, esperado):
    assert limitador.quitar_relleno(peso) == esperado


# --- Ausencia de secretos -----------------------------------------------------------------------------------------------

def test_no_se_guardan_ni_registran_contrasenas_ni_correos(cliente, base, caplog):
    correo = "Persona.Distintiva@Nahan.local"
    clave = "contrasena-muy-distintiva-987"

    with caplog.at_level(logging.DEBUG):
        respuestas = [_intentar(cliente, correo, clave, IP_B) for _ in range(6)]
        respuestas.append(_intentar(cliente, ADMIN, clave, IP_B))
        base.bloqueos[BLOQUEO] = "ajeno"
        respuestas.append(_intentar(cliente, JURIDICA, clave, IP_C))
        del base.bloqueos[BLOQUEO]
        base.inyectar_fallo("SELECT (SELECT COUNT(*)", _error_mysql(1146), 1)
        respuestas.append(_intentar(cliente, JURIDICA, clave, IP_C))

    volcado = json.dumps([[repr(v) for v in fila.values()] for fila in _filas(base)]).lower()
    for secreto in (clave, correo, correo.lower(), "persona.distintiva", "persona"):
        assert secreto.lower() not in volcado
        assert secreto.lower() not in caplog.text.lower()
        assert all(secreto.lower() not in r.get_data(as_text=True).lower() for r in respuestas)
    for fila in _filas(base):
        assert len(fila["clave_cuenta"]) == 32
        assert fila["clave_cuenta"] != correo.lower().encode()
        assert set(fila) == {"id_intento", "clave_cuenta", "ip_cliente", "id_usuario", "fecha"}


def test_las_filas_guardan_el_id_de_usuario_solo_para_cuentas_existentes(cliente, base):
    _intentar(cliente, ADMIN, INCORRECTA)
    _intentar(cliente, "fantasma@nahan.local", INCORRECTA)

    assert [f["id_usuario"] for f in _filas(base)] == [1, None]


# --- Auditoría funcional intacta (RF30) --------------------------------------------------------------------------------------

def test_los_fallos_y_los_bloqueos_no_escriben_en_la_auditoria(cliente, base):
    _fallar(cliente, 8)
    _intentar(cliente, "fantasma@nahan.local")
    _intentar(cliente, INACTIVA, CLAVE)

    assert _eventos(base) == []


def test_un_login_exitoso_sigue_dejando_un_unico_login_en_la_auditoria(cliente, base):
    _fallar(cliente, 3, JURIDICA)

    assert _intentar(cliente, JURIDICA, CLAVE).status_code == 200

    (evento,) = _eventos(base, "LOGIN")
    assert evento["id_usuario"] == 2 and evento["tabla_afectada"] == "sesion"
    assert len(_eventos(base)) == 1


def test_un_login_bloqueado_no_abre_sesion_ni_audita(cliente, base):
    _fallar(cliente, 5)

    assert _intentar(cliente, ADMIN, CLAVE).status_code == 429

    _sin_sesion(cliente)
    assert _eventos(base) == []


def test_los_limites_no_alteran_otras_rutas_de_autenticacion(cliente, base):
    assert _intentar(cliente, JURIDICA, CLAVE).status_code == 200
    _fallar(cliente, 6, ADMIN, IP_A)

    assert cliente.get("/api/auth/me").status_code == 200
    assert cliente.post("/api/logout").status_code == 200
