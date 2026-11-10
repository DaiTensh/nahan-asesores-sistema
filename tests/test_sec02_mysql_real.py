# -*- coding: utf-8 -*-
"""SEC-02 — Comprobaciones contra un MySQL real y DESECHABLE (opt-in).

Las pruebas de test_sec02_limite_login.py corren sobre SQLite y no pueden
comprobar lo esencial del limitador: la competencia entre solicitudes
simultáneas, el bloqueo con nombre, el collation de los correos ni el SQL
propio de MySQL. Estas sí, pero solo si se pide expresamente:

    NAHAN_TEST_MYSQL_PORT=3399 venv/bin/python -m pytest tests/test_sec02_mysql_real.py

Variables: NAHAN_TEST_MYSQL_PORT (obligatoria; activa el módulo),
NAHAN_TEST_MYSQL_USER (root) y NAHAN_TEST_MYSQL_PASSWORD (vacía). El
servidor debe ser local (127.0.0.1) y NO el MySQL del desarrollador: el módulo
se niega a correr en el puerto 3306. Crea su propia base `nahan_test_sec02_*`
con datos sintéticos y la borra al terminar; no toca ninguna otra.
"""
import os
import random
import sys
import threading

import mysql.connector
import pytest

import backend.utils.limitador_login as limitador
from backend.app import app as flask_app
from backend.utils.security import hash_password

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "database"))
import migrar  # noqa: E402

PUERTO = os.getenv("NAHAN_TEST_MYSQL_PORT")

pytestmark = pytest.mark.skipif(
    not PUERTO, reason="opt-in: defina NAHAN_TEST_MYSQL_PORT con el puerto de un MySQL local desechable")

CLAVE = "Clave-Prueba-Real-1"
MALA = "clave-equivocada"
BLOQUEO = "nahan:login:reserva"

ESQUEMA = """
CREATE TABLE rol (id_rol INT AUTO_INCREMENT PRIMARY KEY, nombre_rol VARCHAR(50) NOT NULL UNIQUE);
CREATE TABLE area (id_area INT AUTO_INCREMENT PRIMARY KEY, nombre_area VARCHAR(100) NOT NULL UNIQUE);
CREATE TABLE usuario (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY, id_rol INT NOT NULL, id_area INT NOT NULL,
    nombres VARCHAR(100) NOT NULL, email VARCHAR(150) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL,
    estado ENUM('ACTIVO','INACTIVO') NOT NULL DEFAULT 'ACTIVO', debe_cambiar_password INTEGER DEFAULT 0, version_credenciales INTEGER DEFAULT 0);
CREATE TABLE auditoria (
    id_auditoria INT AUTO_INCREMENT PRIMARY KEY, id_usuario INT NOT NULL, tabla_afectada VARCHAR(100) NOT NULL,
    id_registro INT NULL, accion VARCHAR(50) NOT NULL, datos_anteriores TEXT, datos_nuevos TEXT,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_auditoria_usuario FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario));
INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_JURIDICA');
INSERT INTO area (nombre_area) VALUES ('ADMINISTRACION'), ('JURIDICA');
"""


def _conectar(base=None):
    return mysql.connector.connect(
        host="127.0.0.1", port=int(PUERTO), database=base,
        user=os.getenv("NAHAN_TEST_MYSQL_USER", "root"),
        password=os.getenv("NAHAN_TEST_MYSQL_PASSWORD", ""))


@pytest.fixture(scope="module")
def mysql_real():
    assert PUERTO != "3306", "NAHAN_TEST_MYSQL_PORT no puede apuntar al MySQL del desarrollador (3306)"
    nombre = f"nahan_test_sec02_{os.getpid()}"
    servidor = _conectar()
    cur = servidor.cursor()
    cur.execute(f"CREATE DATABASE {nombre} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    servidor.database = nombre
    for sentencia in ESQUEMA.split(";"):
        if sentencia.strip():
            cur.execute(sentencia)
    for sentencia in migrar.sentencias(os.path.join(RAIZ, "database", "migraciones", "008_intento_login_fallido.sql")):
        cur.execute(sentencia)
    hash_clave = hash_password(CLAVE)
    for i in range(1, 4):
        cur.execute("INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) VALUES (2, 2, %s, %s, %s)",
                    (f"Usuario {i}", f"u{i}@t.test", hash_clave))
    servidor.commit()

    entorno = pytest.MonkeyPatch()
    entorno.setenv("DB_HOST", "127.0.0.1")
    entorno.setenv("DB_PORT", PUERTO)
    entorno.setenv("DB_USER", os.getenv("NAHAN_TEST_MYSQL_USER", "root"))
    entorno.setenv("DB_PASSWORD", os.getenv("NAHAN_TEST_MYSQL_PASSWORD", ""))
    entorno.setenv("DB_NAME", nombre)
    flask_app.config["TESTING"] = True
    try:
        yield servidor
    finally:
        entorno.undo()
        cur.execute(f"DROP DATABASE {nombre}")
        servidor.close()


@pytest.fixture
def db(mysql_real):
    cur = mysql_real.cursor()
    cur.execute("DELETE FROM intento_login_fallido")
    cur.execute("DELETE FROM auditoria")
    mysql_real.commit()
    yield mysql_real
    mysql_real.rollback()


def _q(db, sql, params=()):
    cur = db.cursor()
    cur.execute(sql, params)
    filas = cur.fetchall() if cur.with_rows else []
    db.commit()
    return filas


def _filas(db):
    return _q(db, "SELECT COUNT(*) FROM intento_login_fallido")[0][0]


def _disparar(peticiones):
    """Lanza las peticiones (email, clave, ip) a la vez. Devuelve [(código, Retry-After)]."""
    resultados = [None] * len(peticiones)
    barrera = threading.Barrier(len(peticiones))

    def hilo(i, email, clave, ip):
        cliente = flask_app.test_client()
        barrera.wait()
        r = cliente.post("/api/login", json={"email": email, "password": clave},
                         environ_overrides={"REMOTE_ADDR": ip})
        resultados[i] = (r.status_code, r.headers.get("Retry-After"))

    hilos = [threading.Thread(target=hilo, args=(i, *p)) for i, p in enumerate(peticiones)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    return resultados


def _codigos(resultados):
    cuenta = {}
    for codigo, _ in resultados:
        cuenta[codigo] = cuenta.get(codigo, 0) + 1
    return cuenta


# --- Esquema y migración ----------------------------------------------------------------------

def test_la_migracion_008_es_reconocida_y_repetible(db):
    cur = db.cursor()
    assert migrar.aplicada(cur, "008") is True
    for sentencia in migrar.sentencias(os.path.join(RAIZ, "database", "migraciones", "008_intento_login_fallido.sql")):
        cur.execute(sentencia)      # CREATE TABLE IF NOT EXISTS: repetirla no falla
    assert migrar.aplicada(cur, "008") is True


def test_los_recuentos_usan_los_indices(db):
    cur = db.cursor()
    cur.executemany(
        "INSERT INTO intento_login_fallido (clave_cuenta, ip_cliente, fecha) "
        "VALUES (UNHEX(SHA2(%s, 256)), UNHEX(LPAD(HEX(%s), 8, '0')), UTC_TIMESTAMP() - INTERVAL %s MINUTE)",
        [(f"k{i % 300}", i % 200, i % 40) for i in range(5000)])
    cur.execute("ANALYZE TABLE intento_login_fallido")
    cur.fetchall()
    db.commit()
    for condicion in ("clave_cuenta = UNHEX(SHA2('k1', 256)) AND ip_cliente = UNHEX('00000001')",
                      "clave_cuenta = UNHEX(SHA2('k1', 256))", "ip_cliente = UNHEX('00000001')"):
        cur.execute(f"EXPLAIN FORMAT=TRADITIONAL SELECT COUNT(*) FROM intento_login_fallido WHERE {condicion} "
                    "AND fecha > DATE_SUB(UTC_TIMESTAMP(), INTERVAL 15 MINUTE)")
        assert cur.fetchall()[0][6] in ("idx_ilf_cuenta", "idx_ilf_ip"), f"sin índice para: {condicion}"


# --- Equivalencia de correos con el collation de MySQL ---------------------------------------------------

CORREOS = [
    "juan@nahan.cl", "Juan@Nahan.cl", "JUAN@NAHAN.CL", "josé@nahan.cl", "JOSE@nahan.cl", "josé@nahan.cl",
    "ana@nahan.cl", "ana@nahan.cl ", "ana@nahan.cl   ", "ana@nahan.cl ", "ana@nahan.cl　", " ana@nahan.cl",
    "strasse@nahan.cl", "straße@nahan.cl", "aelita@nahan.cl", "ælita@nahan.cl", "Ælita@nahan.cl",
    "ａｎａ@nahan.cl", "ana＠nahan.cl", "ju­an@nahan.cl", "ju​an@nahan.cl", "ju\x01an@nahan.cl",
    "😀@nahan.cl", "😁@nahan.cl", "аna@nahan.cl", "a.b@nahan.cl", "ab@nahan.cl", "", " ", " ",
]


def test_la_clave_de_cuenta_equivale_a_la_comparacion_de_mysql(db):
    random.seed(20261014)
    alfabeto = list("aAnNeEsSx@. ") + ["é", "ß", "æ", "Æ", "ａ", "­", "​", " ", "　", "\x01",
                                       "😀", "😁", "ǆ", "а", "́"]
    cadenas = sorted(set(CORREOS) | {"".join(random.choice(alfabeto) for _ in range(random.randint(0, 6)))
                                      for _ in range(300)})
    cur = db.cursor(dictionary=True)
    cur.execute("DROP TABLE IF EXISTS prueba_correo")
    cur.execute("CREATE TABLE prueba_correo (id INT AUTO_INCREMENT PRIMARY KEY, email VARCHAR(150) NOT NULL, "
                "KEY ix (email)) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
    cur.executemany("INSERT INTO prueba_correo (email) VALUES (%s)", [(c,) for c in cadenas])
    db.commit()
    cur.execute("SELECT id, email FROM prueba_correo")
    correos = {fila["id"]: fila["email"] for fila in cur.fetchall()}
    with flask_app.test_request_context():
        claves = {i: limitador.calcular_clave_cuenta(cur, e) for i, e in correos.items()}
    iguales = set()
    for i, e in correos.items():
        cur.execute("SELECT id FROM prueba_correo WHERE email = %s", (e,))   # como el WHERE del login
        iguales |= {(i, fila["id"]) for fila in cur.fetchall()}
    discrepancias = [(correos[i], correos[j]) for i in correos for j in correos
                     if ((i, j) in iguales) != (claves[i] == claves[j])]
    cur.execute("DROP TABLE prueba_correo")
    assert discrepancias == []
    assert all(len(c) == 32 for c in claves.values())


# --- Concurrencia -------------------------------------------------------------------------------------------

def test_veinte_solicitudes_simultaneas_al_mismo_par_reservan_exactamente_cinco(db):
    for _ in range(4):
        _q(db, "DELETE FROM intento_login_fallido")
        codigos = _codigos(_disparar([("u1@t.test", MALA, "203.0.113.20")] * 20))
        assert codigos == {401: 5, 429: 15}
        assert _filas(db) == 5
        assert _q(db, "SELECT IS_USED_LOCK(%s)", (BLOQUEO,))[0][0] is None


def test_muchas_ip_contra_una_cuenta_no_superan_el_tope_de_la_cuenta(db):
    for _ in range(3):
        _q(db, "DELETE FROM intento_login_fallido")
        codigos = _codigos(_disparar([("u2@t.test", MALA, f"198.51.100.{i // 2 + 1}") for i in range(40)]))
        assert codigos == {401: 15, 429: 25}
        assert _filas(db) == 15
        assert _q(db, "SELECT MAX(n) FROM (SELECT COUNT(*) AS n FROM intento_login_fallido GROUP BY ip_cliente) t")[0][0] <= 5


def test_una_ip_contra_muchas_cuentas_no_supera_el_tope_de_la_ip(db):
    for _ in range(2):
        _q(db, "DELETE FROM intento_login_fallido")
        codigos = _codigos(_disparar([(f"nadie{i}@t.test", MALA, "192.0.2.9") for i in range(60)]))
        assert codigos == {401: 40, 429: 20}
        assert _filas(db) == 40


def test_un_login_correcto_concurrente_con_fallos_nunca_queda_sin_auditoria(db):
    for _ in range(4):
        _q(db, "DELETE FROM intento_login_fallido")
        _q(db, "DELETE FROM auditoria")
        # Caben las 5 reservas (4 fallos + el éxito): nadie debe recibir 429.
        codigos = _codigos(_disparar([("u3@t.test", MALA, "203.0.113.30")] * 4 + [("u3@t.test", CLAVE, "203.0.113.30")]))
        assert codigos == {200: 1, 401: 4}
        assert _filas(db) == 4
        assert _q(db, "SELECT COUNT(*) FROM auditoria WHERE accion = 'LOGIN'")[0][0] == 1
        # Saturado: nunca más de 5 reservas, y cada 200 tiene exactamente un LOGIN auditado.
        _q(db, "DELETE FROM intento_login_fallido")
        _q(db, "DELETE FROM auditoria")
        codigos = _codigos(_disparar([("u3@t.test", MALA, "203.0.113.31")] * 8 + [("u3@t.test", CLAVE, "203.0.113.31")]))
        assert set(codigos) <= {200, 401, 429}
        assert _filas(db) <= 5
        assert _q(db, "SELECT COUNT(*) FROM auditoria WHERE accion = 'LOGIN'")[0][0] == codigos.get(200, 0)


def test_un_bloqueo_retenido_por_otra_conexion_responde_503_y_se_recupera(db):
    otra = _conectar()
    cur = otra.cursor()
    cur.execute("SELECT GET_LOCK(%s, 0)", (BLOQUEO,))
    cur.fetchall()
    try:
        (codigo, retry), = _disparar([("u1@t.test", CLAVE, "203.0.113.40")])
        assert (codigo, retry) == (503, "2")
        assert _filas(db) == 0
    finally:
        otra.close()      # cerrar la conexión libera el bloqueo
    (codigo, _), = _disparar([("u1@t.test", CLAVE, "203.0.113.40")])
    assert codigo == 200
    assert _q(db, "SELECT IS_USED_LOCK(%s)", (BLOQUEO,))[0][0] is None


def test_la_purga_concurrente_borra_lotes_de_500_sin_errores(db):
    cur = db.cursor()
    cur.executemany("INSERT INTO intento_login_fallido (clave_cuenta, ip_cliente, id_usuario, fecha) "
                    "VALUES (%s, NULL, NULL, UTC_TIMESTAMP() - INTERVAL 30 HOUR)", [(b"\x01" * 32,)] * 2500)
    db.commit()
    codigos = _codigos(_disparar([(f"p{i}@t.test", MALA, f"198.18.{i % 6}.{i % 250 + 1}") for i in range(120)]))
    vencidas = _q(db, "SELECT COUNT(*) FROM intento_login_fallido WHERE fecha < UTC_TIMESTAMP() - INTERVAL 24 HOUR")[0][0]
    assert set(codigos) <= {401, 429}, "ni 500 ni 503 con la purga en marcha"
    assert (2500 - vencidas) % 500 == 0 and vencidas < 2500
    for nombre in (BLOQUEO, "nahan:login:purga"):
        assert _q(db, "SELECT IS_USED_LOCK(%s)", (nombre,))[0][0] is None
