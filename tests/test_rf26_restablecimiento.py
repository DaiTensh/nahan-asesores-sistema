# -*- coding: utf-8 -*-
"""RF26 — Restableciendo Contraseñas.

Verifica los criterios de aceptación del requerimiento sobre una base SQLite
en memoria que reproduce las tablas involucradas. No necesita un servidor
MySQL, así que corre en cualquier equipo del grupo y en cualquier momento.

Lo que se comprueba es la lógica del flujo: que el token se guarde con hash,
que la respuesta no revele si el correo existe, que el enlace sirva una sola
vez y caduque, y que el aviso interno llegue a los administradores. El
dialecto de MySQL se verifica ejecutando el sistema de verdad.
"""
import hashlib
import re
import sqlite3

import pytest

import backend.routes.auth_routes as auth_routes
from backend.app import app as flask_app
from backend.utils.correo import smtp_configurado

ESQUEMA = """
CREATE TABLE rol (id_rol INTEGER PRIMARY KEY AUTOINCREMENT, nombre_rol TEXT, estado TEXT DEFAULT 'ACTIVO');
CREATE TABLE area (id_area INTEGER PRIMARY KEY AUTOINCREMENT, nombre_area TEXT);
CREATE TABLE usuario (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT, id_rol INTEGER, id_area INTEGER,
    nombres TEXT, email TEXT UNIQUE, password_hash TEXT, estado TEXT DEFAULT 'ACTIVO');
CREATE TABLE notificacion (
    id_notificacion INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER, tipo TEXT,
    mensaje TEXT, url_destino TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP, leida INTEGER DEFAULT 0);
CREATE TABLE token_recuperacion (
    id_token INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    token_hash TEXT UNIQUE NOT NULL, fecha_emision DATETIME DEFAULT CURRENT_TIMESTAMP,
    fecha_expiracion DATETIME NOT NULL, utilizado INTEGER DEFAULT 0, fecha_uso DATETIME);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_JURIDICA');
INSERT INTO area (nombre_area) VALUES ('ADMINISTRACION'), ('JURIDICA');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) VALUES
 (1, 1, 'Renato Villalobos', 'renato.villalobos@nahan.local', 'hash-anterior', 'ACTIVO'),
 (1, 1, 'Matias Rodriguez',  'matias.rodriguez@nahan.local',  'hash-anterior', 'ACTIVO'),
 (2, 2, 'Elias Alarcon',     'elias.alarcon@nahan.local',     'hash-anterior', 'ACTIVO'),
 (2, 2, 'Cuenta Inactiva',   'inactiva@nahan.local',          'hash-anterior', 'INACTIVO');
"""


def _traducir(sql):
    """Lo mínimo para que el SQL del módulo corra sobre SQLite."""
    sql = sql.replace("%s", "?")
    sql = sql.replace("DATE_ADD(NOW(), INTERVAL ? MINUTE)",
                      "datetime('now', '+' || ? || ' minutes')")
    sql = re.sub(r"\bNOW\(\)", "datetime('now')", sql)
    return sql.replace("TRUE", "1").replace("FALSE", "0")


class _Cursor:
    def __init__(self, conexion):
        self._cursor = conexion.cursor()
        self.lastrowid = None

    def execute(self, sql, params=()):
        self._cursor.execute(_traducir(sql), tuple(params))
        self.lastrowid = self._cursor.lastrowid

    def executemany(self, sql, secuencia):
        self._cursor.executemany(_traducir(sql), [tuple(p) for p in secuencia])

    def fetchone(self):
        fila = self._cursor.fetchone()
        return dict(fila) if fila else None

    def fetchall(self):
        return [dict(fila) for fila in self._cursor.fetchall()]

    def close(self):
        pass


class _Conexion:
    def __init__(self, sqlite_conexion):
        self._conexion = sqlite_conexion

    def cursor(self, dictionary=False):
        return _Cursor(self._conexion)

    def commit(self):
        self._conexion.commit()

    def rollback(self):
        self._conexion.rollback()

    def close(self):
        pass


@pytest.fixture
def base():
    conexion = sqlite3.connect(":memory:")
    conexion.row_factory = sqlite3.Row
    conexion.executescript(ESQUEMA)
    conexion.commit()
    yield conexion
    conexion.close()


@pytest.fixture
def correos():
    return []


@pytest.fixture
def cliente(base, correos, monkeypatch):
    monkeypatch.setenv("APP_URL_FRONTEND", "http://127.0.0.1:5500/frontend")
    monkeypatch.setenv("RESET_TOKEN_MINUTOS", "60")
    for clave in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(clave, raising=False)

    monkeypatch.setattr(auth_routes, "get_connection", lambda: _Conexion(base))
    monkeypatch.setattr(
        auth_routes, "enviar_correo",
        lambda destinatario, asunto, cuerpo: correos.append((destinatario, asunto, cuerpo)) or False
    )

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as cliente_http:
        yield cliente_http


def _token(correos):
    return re.search(r"token=([A-Za-z0-9_\-]+)", correos[-1][2]).group(1)


def _filas(base, sql, params=()):
    cursor = base.cursor()
    cursor.execute(sql, params)
    return [dict(f) for f in cursor.fetchall()]


def _solicitar(cliente, email):
    return cliente.post("/api/auth/recuperar", json={"email": email})


def _verificar(cliente, token):
    return cliente.post("/api/auth/recuperar/verificar", json={"token": token}).get_json()["valido"]


# --------------------------------------------------------------------------
def test_solicitud_genera_enlace_y_avisa_a_los_administradores(cliente, base, correos):
    respuesta = _solicitar(cliente, "elias.alarcon@nahan.local")

    assert respuesta.status_code == 200
    assert len(correos) == 1
    assert correos[0][0] == "elias.alarcon@nahan.local"
    assert "restablecer.html?token=" in correos[0][2]

    avisos = _filas(base, "SELECT * FROM notificacion")
    assert len(avisos) == 2, "debe avisarse a los dos administradores activos"
    assert avisos[0]["tipo"] == "SEGURIDAD"
    assert "elias.alarcon@nahan.local" in avisos[0]["mensaje"]


def test_el_token_se_guarda_con_hash_y_no_en_claro(cliente, base, correos):
    _solicitar(cliente, "elias.alarcon@nahan.local")
    token = _token(correos)

    guardado = _filas(base, "SELECT token_hash, utilizado FROM token_recuperacion")[0]

    assert guardado["token_hash"] != token
    assert guardado["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert guardado["utilizado"] == 0


@pytest.mark.parametrize("email", ["noexiste@nahan.local", "inactiva@nahan.local"])
def test_la_respuesta_no_revela_si_la_cuenta_existe(cliente, base, correos, email):
    referencia = _solicitar(cliente, "elias.alarcon@nahan.local").get_json()["message"]
    correos.clear()

    respuesta = _solicitar(cliente, email)

    assert respuesta.status_code == 200
    assert respuesta.get_json()["message"] == referencia
    assert correos == [], "no debe generarse correo para una cuenta que no aplica"
    assert len(_filas(base, "SELECT * FROM token_recuperacion")) == 1


def test_una_solicitud_nueva_invalida_la_anterior(cliente, correos):
    _solicitar(cliente, "elias.alarcon@nahan.local")
    primero = _token(correos)

    _solicitar(cliente, "elias.alarcon@nahan.local")
    segundo = _token(correos)

    assert primero != segundo
    assert _verificar(cliente, primero) is False
    assert _verificar(cliente, segundo) is True


def test_restablecimiento_cambia_la_clave_y_consume_el_token(cliente, base, correos):
    _solicitar(cliente, "elias.alarcon@nahan.local")
    token = _token(correos)
    antes = _filas(base, "SELECT password_hash FROM usuario WHERE email = 'elias.alarcon@nahan.local'")[0]

    respuesta = cliente.post("/api/auth/restablecer", json={"token": token, "password": "clave-nueva-2026"})

    assert respuesta.status_code == 200
    despues = _filas(base, "SELECT password_hash FROM usuario WHERE email = 'elias.alarcon@nahan.local'")[0]
    assert despues["password_hash"] != antes["password_hash"]
    assert despues["password_hash"].startswith("$2b$"), "debe quedar con bcrypt, nunca en claro"

    usado = _filas(base, "SELECT utilizado, fecha_uso FROM token_recuperacion")[0]
    assert usado["utilizado"] == 1
    assert usado["fecha_uso"] is not None


def test_el_enlace_no_sirve_dos_veces(cliente, correos):
    _solicitar(cliente, "elias.alarcon@nahan.local")
    token = _token(correos)
    cliente.post("/api/auth/restablecer", json={"token": token, "password": "clave-nueva-2026"})

    respuesta = cliente.post("/api/auth/restablecer", json={"token": token, "password": "otra-clave-2026"})

    assert respuesta.status_code == 400


def test_el_enlace_caduca(cliente, base, correos):
    _solicitar(cliente, "elias.alarcon@nahan.local")
    token = _token(correos)

    base.execute("UPDATE token_recuperacion SET fecha_expiracion = datetime('now', '-1 hour')")
    base.commit()

    assert _verificar(cliente, token) is False
    assert cliente.post("/api/auth/restablecer",
                        json={"token": token, "password": "clave-nueva-2026"}).status_code == 400


def test_contrasena_corta_se_rechaza_sin_gastar_el_token(cliente, correos):
    _solicitar(cliente, "elias.alarcon@nahan.local")
    token = _token(correos)

    respuesta = cliente.post("/api/auth/restablecer", json={"token": token, "password": "corta"})

    assert respuesta.status_code == 400
    assert "8" in respuesta.get_json()["error"]
    assert _verificar(cliente, token) is True, "un intento fallido no debe invalidar el enlace"


def test_token_inventado_o_ausente_no_es_valido(cliente):
    assert _verificar(cliente, "inventado") is False
    assert cliente.post("/api/auth/recuperar/verificar", json={}).get_json()["valido"] is False


def test_entradas_invalidas_responden_400_y_no_500(cliente):
    assert cliente.post("/api/auth/recuperar", json={}).status_code == 400
    assert cliente.post("/api/auth/restablecer", json={"token": "x"}).status_code == 400
    assert cliente.post("/api/auth/recuperar", data="no es json",
                        content_type="text/plain").status_code == 400


def test_sin_cuenta_configurada_el_sistema_no_intenta_enviar(monkeypatch):
    for clave in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(clave, raising=False)

    assert smtp_configurado() is False
