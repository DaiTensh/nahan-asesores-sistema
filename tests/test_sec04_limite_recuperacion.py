# -*- coding: utf-8 -*-
"""SEC-04 — Límite de solicitudes de recuperación de contraseña por cuenta.

Una cuenta admite como máximo 3 solicitudes efectivas (las que generan un
token) en una ventana móvil de 60 minutos. La cuarta recibe la misma
respuesta genérica, pero no genera token, no invalida el vigente, no avisa a
los administradores y no envía correo.

Corre sobre SQLite en memoria con las rutas reales (mismo arnés que RF26).
SQLite no tiene bloqueos con nombre: aquí se verifica la regla, la ventana y
el orden de las sentencias; la competencia entre solicitudes simultáneas se
prueba contra MySQL/InnoDB aparte.
"""
import pytest

import backend.routes.auth_routes as auth_routes
from tests.test_rf26_restablecimiento import (  # noqa: F401  (fixtures y ayudas del arnés RF26)
    _Conexion,
    _filas,
    _solicitar,
    _token,
    _verificar,
    base,
    cliente,
    correos,
)

ELIAS = "elias.alarcon@nahan.local"
RENATO = "renato.villalobos@nahan.local"


def _tokens(base, email=None):
    sql = "SELECT t.* FROM token_recuperacion t JOIN usuario u ON u.id_usuario = t.id_usuario"
    if email:
        return _filas(base, sql + " WHERE u.email = ? ORDER BY t.id_token", (email,))
    return _filas(base, sql + " ORDER BY t.id_token")


def _avisos(base):
    return _filas(base, "SELECT * FROM notificacion")


def _envejecer(base, minutos, email=None):
    """Retrocede la fecha de emisión de los tokens (todos, o los de una cuenta)."""
    filtro = ""
    parametros = [f"-{minutos} minutes"]
    if email:
        filtro = " WHERE id_usuario = (SELECT id_usuario FROM usuario WHERE email = ?)"
        parametros.append(email)
    base.execute(f"UPDATE token_recuperacion SET fecha_emision = datetime('now', ?){filtro}", parametros)
    base.commit()


def _pedir_tres(cliente, email=ELIAS):
    for _ in range(3):
        assert _solicitar(cliente, email).status_code == 200


# --- 1, 2, 3: las tres primeras solicitudes siguen el flujo de siempre ----------

@pytest.mark.parametrize("numero", [1, 2, 3])
def test_las_tres_primeras_solicitudes_generan_token_aviso_y_correo(cliente, base, correos, numero):
    for _ in range(numero):
        respuesta = _solicitar(cliente, ELIAS)

    assert respuesta.status_code == 200
    assert len(_tokens(base, ELIAS)) == numero
    assert len(correos) == numero
    assert "restablecer.html?token=" in correos[-1][2]
    assert len(_avisos(base)) == 2 * numero, "cada solicitud avisa a los dos administradores activos"


# --- 4 a 9: la cuarta solicitud --------------------------------------------------

def test_la_cuarta_solicitud_responde_igual_y_no_hace_nada(cliente, base, correos):
    referencia = _solicitar(cliente, ELIAS).get_json()
    for _ in range(2):
        _solicitar(cliente, ELIAS)
    vigente = _token(correos)
    tokens_antes = _tokens(base, ELIAS)
    avisos_antes = _avisos(base)
    correos_antes = len(correos)

    respuesta = _solicitar(cliente, ELIAS)

    assert respuesta.status_code == 200
    assert respuesta.get_json() == referencia, "misma respuesta genérica"
    assert _tokens(base, ELIAS) == tokens_antes, "no se genera otro token ni se altera ninguno"
    assert _verificar(cliente, vigente) is True, "el token vigente no se invalida"
    assert len(correos) == correos_antes, "no se envía otro correo"
    assert _avisos(base) == avisos_antes, "no se crean notificaciones adicionales"
    assert [t["utilizado"] for t in _tokens(base, ELIAS)] == [1, 1, 0]


def test_las_solicitudes_siguientes_a_la_cuota_tampoco_hacen_nada(cliente, base, correos):
    _pedir_tres(cliente)
    antes = (_tokens(base), _avisos(base), len(correos))

    for _ in range(10):
        assert _solicitar(cliente, ELIAS).status_code == 200

    assert (_tokens(base), _avisos(base), len(correos)) == antes


def test_superar_la_cuota_no_registra_el_token_en_los_logs(cliente, correos, caplog):
    _pedir_tres(cliente)
    token = _token(correos)
    caplog.clear()

    with caplog.at_level("DEBUG"):
        _solicitar(cliente, ELIAS)

    assert token not in caplog.text
    assert "omitida por límite" in caplog.text


# --- 10: la ventana es móvil y de 60 minutos ----------------------------------------

def test_la_cuota_se_libera_pasados_60_minutos(cliente, base, correos):
    _pedir_tres(cliente)
    assert len(_tokens(base, ELIAS)) == 3
    _envejecer(base, 61)

    _solicitar(cliente, ELIAS)

    assert len(_tokens(base, ELIAS)) == 4
    assert len(correos) == 4
    assert _verificar(cliente, _token(correos)) is True


def test_dentro_de_los_60_minutos_la_cuota_sigue_agotada(cliente, base, correos):
    _pedir_tres(cliente)
    _envejecer(base, 59)

    _solicitar(cliente, ELIAS)

    assert len(_tokens(base, ELIAS)) == 3


def test_la_ventana_es_movil_solo_cuentan_las_solicitudes_recientes(cliente, base, correos):
    _pedir_tres(cliente)
    # La más antigua sale de la ventana; las otras dos siguen dentro.
    base.execute(
        "UPDATE token_recuperacion SET fecha_emision = datetime('now', '-61 minutes') "
        "WHERE id_token = (SELECT MIN(id_token) FROM token_recuperacion)"
    )
    base.commit()

    assert _solicitar(cliente, ELIAS).status_code == 200
    assert len(_tokens(base, ELIAS)) == 4          # entra una nueva: eran 2 dentro de la ventana
    _solicitar(cliente, ELIAS)
    assert len(_tokens(base, ELIAS)) == 4          # ahora son 3 dentro de la ventana: bloqueada


def test_un_token_ya_usado_cuenta_para_la_cuota(cliente, base, correos):
    _solicitar(cliente, ELIAS)
    token = _token(correos)
    assert cliente.post("/api/auth/restablecer", json={"token": token, "password": "Clave-nueva-2026"}).status_code == 200
    _solicitar(cliente, ELIAS)
    _solicitar(cliente, ELIAS)

    _solicitar(cliente, ELIAS)

    assert len(_tokens(base, ELIAS)) == 3


# --- 11, 12, 13: independencia y no enumeración ------------------------------------------

def test_las_cuentas_tienen_cuotas_independientes(cliente, base, correos):
    _pedir_tres(cliente, ELIAS)
    _solicitar(cliente, ELIAS)

    assert _solicitar(cliente, RENATO).status_code == 200

    assert len(_tokens(base, ELIAS)) == 3
    assert len(_tokens(base, RENATO)) == 1
    assert correos[-1][0] == RENATO


def test_el_limite_de_una_cuenta_no_cambia_la_respuesta_para_otras(cliente, correos):
    referencia = _solicitar(cliente, ELIAS).get_json()
    _pedir_tres(cliente, ELIAS)

    limitada = _solicitar(cliente, ELIAS)
    inexistente = _solicitar(cliente, "nadie@nahan.local")
    inactiva = _solicitar(cliente, "inactiva@nahan.local")

    for respuesta in (limitada, inexistente, inactiva):
        assert respuesta.status_code == 200
        assert respuesta.get_json() == referencia


def test_cuentas_inexistentes_e_inactivas_siguen_sin_generar_nada(cliente, base, correos):
    for correo in ("nadie@nahan.local", "inactiva@nahan.local"):
        for _ in range(5):
            assert _solicitar(cliente, correo).status_code == 200

    assert _tokens(base) == []
    assert correos == []
    assert _avisos(base) == []


def test_no_se_usa_429_ni_se_revela_el_limite(cliente):
    _pedir_tres(cliente)

    respuesta = _solicitar(cliente, ELIAS)

    assert respuesta.status_code == 200
    assert set(respuesta.get_json()) == {"message"}
    assert "retry-after" not in {nombre.lower() for nombre in respuesta.headers.keys()}


# --- 14, 15: comportamiento del token dentro de la cuota ------------------------------------

def test_una_solicitud_permitida_invalida_el_token_anterior(cliente, correos):
    _solicitar(cliente, ELIAS)
    primero = _token(correos)
    _solicitar(cliente, ELIAS)
    segundo = _token(correos)

    assert _verificar(cliente, primero) is False
    assert _verificar(cliente, segundo) is True


def test_el_token_sigue_siendo_de_un_solo_uso_tambien_con_cuota_agotada(cliente, base, correos):
    _pedir_tres(cliente)
    token = _token(correos)

    assert cliente.post("/api/auth/restablecer", json={"token": token, "password": "Clave-nueva-2026"}).status_code == 200
    assert cliente.post("/api/auth/restablecer", json={"token": token, "password": "Otra-clave-2026"}).status_code == 400
    assert _verificar(cliente, token) is False


# --- Orden de sentencias y bloqueo ------------------------------------------------------------

class _Grabadora(_Conexion):
    """Conexión de pruebas que anota las sentencias, los rollback/commit y los correos."""

    def __init__(self, sqlite_conexion, eventos):
        super().__init__(sqlite_conexion)
        self.eventos = eventos

    def cursor(self, dictionary=False):
        cursor = super().cursor(dictionary)
        original = cursor.execute

        def grabar(sql, params=()):
            self.eventos.append(("sql", " ".join(sql.split()), tuple(params)))
            return original(sql, params)

        cursor.execute = grabar
        return cursor

    def commit(self):
        self.eventos.append(("commit",))
        super().commit()

    def rollback(self):
        self.eventos.append(("rollback",))
        super().rollback()


@pytest.fixture
def eventos(base, correos, monkeypatch):
    registro = []
    monkeypatch.setattr(auth_routes, "get_connection", lambda: _Grabadora(base, registro))
    monkeypatch.setattr(
        auth_routes, "enviar_correo",
        lambda destinatario, asunto, cuerpo: registro.append(("correo",)) or correos.append((destinatario, asunto, cuerpo)) or False,
    )
    return registro


def _posicion(eventos, predicado):
    return next(i for i, e in enumerate(eventos) if predicado(e))


def test_el_bloqueo_precede_al_conteo_y_se_libera_antes_de_enviar_el_correo(cliente, eventos):
    _solicitar(cliente, ELIAS)

    bloqueo = _posicion(eventos, lambda e: e[0] == "sql" and "GET_LOCK" in e[1])
    final_lectura = _posicion(eventos, lambda e: e[0] == "rollback")
    conteo = _posicion(eventos, lambda e: e[0] == "sql" and "COUNT(*)" in e[1] and "token_recuperacion" in e[1])
    insercion = _posicion(eventos, lambda e: e[0] == "sql" and e[1].startswith("INSERT INTO token_recuperacion"))
    confirmacion = _posicion(eventos, lambda e: e[0] == "commit")
    liberacion = _posicion(eventos, lambda e: e[0] == "sql" and "RELEASE_LOCK" in e[1])
    correo = _posicion(eventos, lambda e: e[0] == "correo")

    # El conteo parte de una instantánea nueva tomada con el bloqueo en mano.
    assert bloqueo < final_lectura < conteo < insercion < confirmacion < liberacion < correo
    assert eventos[bloqueo][2][0] == "nahan:recuperar:3"  # Elías es el usuario 3


def test_si_no_se_obtiene_el_bloqueo_se_responde_igual_y_no_se_hace_nada(cliente, base, correos, eventos, monkeypatch):
    monkeypatch.setattr(auth_routes, "_adquirir_bloqueo_recuperacion", lambda cursor, id_usuario: False)

    respuesta = _solicitar(cliente, ELIAS)

    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"message": auth_routes.MENSAJE_SOLICITUD}
    assert _tokens(base) == [] and correos == [] and _avisos(base) == []


def test_al_superar_la_cuota_el_bloqueo_se_libera(cliente, eventos):
    _pedir_tres(cliente)
    eventos.clear()

    _solicitar(cliente, ELIAS)

    assert sum(1 for e in eventos if e[0] == "sql" and "GET_LOCK" in e[1]) == 1
    assert sum(1 for e in eventos if e[0] == "sql" and "RELEASE_LOCK" in e[1]) == 1
    assert not any(e[0] == "sql" and e[1].startswith(("INSERT", "UPDATE")) for e in eventos)


def test_un_error_libera_el_bloqueo_y_no_deja_cambios(cliente, base, correos, eventos, monkeypatch):
    def fallar(cursor, usuario):
        raise RuntimeError("fallo al avisar")

    monkeypatch.setattr(auth_routes, "_avisar_a_administradores", fallar)

    respuesta = _solicitar(cliente, ELIAS)

    assert respuesta.status_code == 500
    assert _tokens(base) == [] and correos == []
    assert sum(1 for e in eventos if e[0] == "sql" and "RELEASE_LOCK" in e[1]) == 1


def test_las_cuentas_inexistentes_no_toman_bloqueo(cliente, eventos):
    _solicitar(cliente, "nadie@nahan.local")

    assert not any(e[0] == "sql" and "GET_LOCK" in e[1] for e in eventos)
