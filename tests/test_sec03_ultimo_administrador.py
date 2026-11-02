# -*- coding: utf-8 -*-
"""SEC-03 — El sistema debe conservar siempre al menos un administrador activo.

Cubre los tres endpoints que pueden reducir el conjunto de administradores
activos:

    PUT /api/usuarios/<id>/desactivar
    PUT /api/usuarios/<id>/rol
    PUT /api/usuarios/<id>

Corre sobre SQLite en memoria con las rutas reales. SQLite no tiene bloqueos
de fila, así que aquí se verifica la regla, el rollback y el orden de las
sentencias; la competencia entre dos conexiones simultáneas solo puede
probarse contra MySQL/InnoDB (ver el procedimiento de la intervención).
"""
import re
import sqlite3

import pytest
from mysql.connector.errors import DatabaseError

import backend.routes.usuarios_routes as usuarios_routes
from tests.conftest import FakeConnection, normalize_sql

MENSAJE = (
    "No se puede realizar esta operación porque el sistema debe conservar "
    "al menos un administrador activo."
)

ESQUEMA = """
CREATE TABLE usuario (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT, id_rol INTEGER, id_area INTEGER,
    nombres TEXT, email TEXT UNIQUE, password_hash TEXT, estado TEXT DEFAULT 'ACTIVO');
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tabla_afectada TEXT, id_registro INTEGER, accion TEXT, datos_anteriores TEXT,
    datos_nuevos TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP);
"""

AREA_POR_ROL = {1: 3, 2: 1, 3: 2}


def _traducir(sql):
    sql = sql.replace("%s", "?")
    # SQLite no tiene bloqueos de fila: se descarta solo el sufijo.
    return re.sub(r"\s+FOR UPDATE\s*$", "", sql)


class _Cursor:
    def __init__(self, conexion):
        self._cursor = conexion.cursor()
        self.lastrowid = None
        self.rowcount = 0

    def execute(self, sql, params=()):
        self._cursor.execute(_traducir(sql), tuple(params))
        self.lastrowid = self._cursor.lastrowid
        self.rowcount = self._cursor.rowcount

    def fetchone(self):
        fila = self._cursor.fetchone()
        return tuple(fila) if fila is not None else None

    def fetchall(self):
        return [tuple(fila) for fila in self._cursor.fetchall()]

    def close(self):
        pass


class _Conexion:
    def __init__(self, sqlite_conexion):
        self._conexion = sqlite_conexion
        self.rollbacks = 0
        self.commits = 0

    def cursor(self, dictionary=False):
        return _Cursor(self._conexion)

    def commit(self):
        self.commits += 1
        self._conexion.commit()

    def rollback(self):
        self.rollbacks += 1
        self._conexion.rollback()

    def close(self):
        pass


def _montar(usuarios):
    """usuarios: lista de (id_rol, estado). El id es la posición (desde 1)."""
    base = sqlite3.connect(":memory:")
    base.executescript(ESQUEMA)
    for posicion, (id_rol, estado) in enumerate(usuarios, start=1):
        base.execute(
            "INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) "
            "VALUES (?, ?, ?, ?, 'x', ?)",
            (id_rol, AREA_POR_ROL[id_rol], f"Usuario {posicion}", f"u{posicion}@nahan.test", estado),
        )
    base.commit()
    return base


@pytest.fixture
def entorno(client, iniciar_sesion, monkeypatch):
    """Devuelve una función que monta la base y deja iniciada la sesión del actor."""
    abiertas = []

    def preparar(usuarios, actor=1):
        base = _montar(usuarios)
        conexion = _Conexion(base)
        monkeypatch.setattr(usuarios_routes, "get_connection", lambda: conexion)
        iniciar_sesion(usuario_id=actor, rol_id=1, area_id=3)
        abiertas.append(base)
        return base, conexion

    yield preparar
    for base in abiertas:
        base.close()


def _estado(base, id_usuario):
    fila = base.execute(
        "SELECT id_rol, id_area, estado FROM usuario WHERE id_usuario = ?", (id_usuario,)
    ).fetchone()
    return tuple(fila)


def _eventos(base):
    return base.execute("SELECT accion, id_registro FROM auditoria ORDER BY id_auditoria").fetchall()


def _administradores_activos(base):
    return base.execute(
        "SELECT COUNT(*) FROM usuario WHERE id_rol = 1 AND estado = 'ACTIVO'"
    ).fetchone()[0]


# Operaciones sobre un usuario. Cada una intenta DEJAR de ser administrador
# activo (las dos primeras de la lista) o lo conserva.
def _desactivar(client, id_usuario):
    return client.put(f"/api/usuarios/{id_usuario}/desactivar")


def _quitar_rol(client, id_usuario):
    return client.put(f"/api/usuarios/{id_usuario}/rol", json={"id_rol": 2})


def _actualizar(client, id_usuario, *, id_rol, estado):
    return client.put(
        f"/api/usuarios/{id_usuario}",
        json={
            "id_rol": id_rol,
            "id_area": AREA_POR_ROL[id_rol],
            "nombres": f"Usuario {id_usuario}",
            "email": f"u{id_usuario}@nahan.test",
            "estado": estado,
        },
    )


# Las cuatro formas de sacar a un administrador activo del conjunto.
SACAN_AL_ADMINISTRADOR = [
    pytest.param(lambda c, i: _desactivar(c, i), id="desactivar"),
    pytest.param(lambda c, i: _quitar_rol(c, i), id="rol"),
    pytest.param(lambda c, i: _actualizar(c, i, id_rol=1, estado="INACTIVO"), id="actualizar-estado"),
    pytest.param(lambda c, i: _actualizar(c, i, id_rol=2, estado="ACTIVO"), id="actualizar-rol"),
    pytest.param(lambda c, i: _actualizar(c, i, id_rol=3, estado="INACTIVO"), id="actualizar-rol-y-estado"),
]


# --- 1, 2, 3: el único administrador activo -------------------------------

@pytest.mark.parametrize("operacion", SACAN_AL_ADMINISTRADOR)
def test_no_se_puede_sacar_al_unico_administrador_activo(client, entorno, operacion):
    base, conexion = entorno([(1, "ACTIVO"), (2, "ACTIVO")], actor=1)
    antes = _estado(base, 1)

    respuesta = operacion(client, 1)

    assert respuesta.status_code == 409
    assert respuesta.get_json() == {"error": MENSAJE}
    assert _estado(base, 1) == antes
    assert _administradores_activos(base) == 1
    assert _eventos(base) == []
    assert conexion.rollbacks == 1 and conexion.commits == 0


# --- 4, 5: existen dos administradores activos -----------------------------

@pytest.mark.parametrize("operacion", SACAN_AL_ADMINISTRADOR)
def test_con_dos_administradores_se_puede_sacar_a_uno(client, entorno, operacion):
    base, conexion = entorno([(1, "ACTIVO"), (1, "ACTIVO")], actor=1)

    respuesta = operacion(client, 2)

    assert respuesta.status_code == 200
    assert _administradores_activos(base) == 1
    assert conexion.commits == 1 and conexion.rollbacks == 0
    assert len(_eventos(base)) == 1


def test_con_dos_administradores_no_se_pueden_sacar_los_dos(client, entorno):
    base, _ = entorno([(1, "ACTIVO"), (1, "ACTIVO")], actor=1)

    assert _desactivar(client, 2).status_code == 200
    assert _quitar_rol(client, 1).status_code == 409

    assert _administradores_activos(base) == 1


# --- 6: usuarios que no son administradores --------------------------------

@pytest.mark.parametrize("operacion", [
    pytest.param(lambda c, i: _desactivar(c, i), id="desactivar"),
    pytest.param(lambda c, i: c.put(f"/api/usuarios/{i}/rol", json={"id_rol": 3}), id="rol"),
    pytest.param(lambda c, i: _actualizar(c, i, id_rol=3, estado="INACTIVO"), id="actualizar"),
])
def test_un_usuario_no_administrador_se_modifica_con_normalidad(client, entorno, operacion):
    base, _ = entorno([(1, "ACTIVO"), (2, "ACTIVO")], actor=1)

    assert operacion(client, 2).status_code == 200
    assert _administradores_activos(base) == 1


# --- 7: administradores inactivos -------------------------------------------

@pytest.mark.parametrize("operacion", [
    pytest.param(lambda c, i: _desactivar(c, i), id="desactivar"),
    pytest.param(lambda c, i: _quitar_rol(c, i), id="rol"),
    pytest.param(lambda c, i: _actualizar(c, i, id_rol=2, estado="INACTIVO"), id="actualizar"),
])
def test_un_administrador_inactivo_se_puede_modificar(client, entorno, operacion):
    base, _ = entorno([(1, "ACTIVO"), (1, "INACTIVO")], actor=1)

    assert operacion(client, 2).status_code == 200
    assert _administradores_activos(base) == 1


def test_un_administrador_inactivo_no_cuenta_como_respaldo(client, entorno):
    base, _ = entorno([(1, "ACTIVO"), (1, "INACTIVO")], actor=1)

    assert _desactivar(client, 1).status_code == 409
    assert _administradores_activos(base) == 1


# --- 8, 9: autooperación -----------------------------------------------------

@pytest.mark.parametrize("operacion", SACAN_AL_ADMINISTRADOR)
def test_el_ultimo_administrador_no_puede_sacarse_a_si_mismo(client, entorno, operacion):
    base, _ = entorno([(1, "ACTIVO")], actor=1)

    respuesta = operacion(client, 1)

    assert respuesta.status_code == 409
    assert _administradores_activos(base) == 1


@pytest.mark.parametrize("operacion", SACAN_AL_ADMINISTRADOR)
def test_un_administrador_puede_sacarse_a_si_mismo_si_hay_otro(client, entorno, operacion):
    base, _ = entorno([(1, "ACTIVO"), (1, "ACTIVO")], actor=2)

    assert operacion(client, 2).status_code == 200
    assert _administradores_activos(base) == 1


# --- Lo que no debe cambiar --------------------------------------------------

@pytest.mark.parametrize("id_rol, estado", [(1, "ACTIVO")])
def test_el_unico_administrador_puede_editar_sus_datos_sin_perder_el_rol(client, entorno, id_rol, estado):
    base, _ = entorno([(1, "ACTIVO")], actor=1)

    respuesta = client.put("/api/usuarios/1", json={
        "id_rol": id_rol, "id_area": 3, "nombres": "Nombre Nuevo",
        "email": "u1@nahan.test", "estado": estado})

    assert respuesta.status_code == 200
    assert base.execute("SELECT nombres FROM usuario WHERE id_usuario = 1").fetchone()[0] == "Nombre Nuevo"


def test_reasignar_el_rol_de_administrador_al_unico_administrador_es_valido(client, entorno):
    base, _ = entorno([(1, "ACTIVO")], actor=1)

    assert client.put("/api/usuarios/1/rol", json={"id_rol": 1}).status_code == 200
    assert _administradores_activos(base) == 1


def test_promover_a_otro_usuario_a_administrador_sigue_permitido(client, entorno):
    base, _ = entorno([(1, "ACTIVO"), (2, "ACTIVO")], actor=1)

    assert client.put("/api/usuarios/2/rol", json={"id_rol": 1}).status_code == 200
    assert _administradores_activos(base) == 2


def test_una_operacion_permitida_conserva_la_auditoria_existente(client, entorno):
    base, _ = entorno([(1, "ACTIVO"), (1, "ACTIVO")], actor=1)

    _desactivar(client, 2)

    (evento,) = _eventos(base)
    assert tuple(evento) == ("USUARIO_DESACTIVADO", 2)


def test_un_usuario_inexistente_sigue_respondiendo_404(client, entorno):
    base, _ = entorno([(1, "ACTIVO")], actor=1)

    assert _desactivar(client, 99).status_code == 404
    assert _quitar_rol(client, 99).status_code == 404
    assert _actualizar(client, 99, id_rol=2, estado="ACTIVO").status_code == 404
    assert _administradores_activos(base) == 1


def test_un_no_administrador_sigue_recibiendo_403(client, iniciar_sesion):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    assert _desactivar(client, 1).status_code == 403
    assert _quitar_rol(client, 1).status_code == 403
    assert _actualizar(client, 1, id_rol=2, estado="INACTIVO").status_code == 403


# --- 10: rollback y errores de concurrencia ------------------------------------

@pytest.mark.parametrize("errno", [1213, 1205], ids=["deadlock", "lock-wait-timeout"])
@pytest.mark.parametrize("operacion", [
    pytest.param(lambda c: _desactivar(c, 2), id="desactivar"),
    pytest.param(lambda c: _quitar_rol(c, 2), id="rol"),
    pytest.param(lambda c: _actualizar(c, 2, id_rol=2, estado="ACTIVO"), id="actualizar"),
])
def test_un_error_de_bloqueo_responde_409_y_revierte_sin_cambios(client, entorno, monkeypatch, operacion, errno):
    base, conexion = entorno([(1, "ACTIVO"), (1, "ACTIVO")], actor=1)
    antes = _estado(base, 2)

    def competir(*args, **kwargs):
        raise DatabaseError(msg="bloqueo", errno=errno)

    monkeypatch.setattr(usuarios_routes, "_conserva_un_administrador_activo", competir)

    respuesta = operacion(client)

    assert respuesta.status_code == 409
    assert "conflicto" in respuesta.get_json()["error"]
    assert conexion.rollbacks == 1 and conexion.commits == 0
    assert _estado(base, 2) == antes
    assert _eventos(base) == []


def test_otros_errores_de_base_de_datos_siguen_siendo_500(client, entorno, monkeypatch):
    entorno([(1, "ACTIVO"), (1, "ACTIVO")], actor=1)

    def fallar(*args, **kwargs):
        raise DatabaseError(msg="otro fallo", errno=1064)

    monkeypatch.setattr(usuarios_routes, "_conserva_un_administrador_activo", fallar)

    assert _desactivar(client, 2).status_code == 500


# --- Orden de las sentencias (condición del esquema de bloqueos) ---------------

@pytest.mark.parametrize("peticion", [
    pytest.param(lambda c: _desactivar(c, 2), id="desactivar"),
    pytest.param(lambda c: _quitar_rol(c, 2), id="rol"),
    pytest.param(lambda c: _actualizar(c, 2, id_rol=2, estado="ACTIVO"), id="actualizar"),
])
def test_la_primera_sentencia_bloquea_a_los_administradores_en_orden(client, iniciar_sesion, monkeypatch, peticion):
    """El bloqueo debe ser lo primero de la transacción y en orden ascendente
    de id: así la instantánea de lectura se crea después de tomar los
    bloqueos y todas las solicitudes bloquean en el mismo orden."""
    conexion = FakeConnection(lambda sql, params, cursor: [])
    monkeypatch.setattr(usuarios_routes, "get_connection", lambda: conexion)
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    peticion(client)

    primera, parametros = conexion.executed[0]
    assert normalize_sql(primera) == (
        "SELECT id_usuario FROM usuario WHERE id_rol = %s AND estado = 'ACTIVO' "
        "ORDER BY id_usuario FOR UPDATE"
    )
    assert parametros == (1,)
    resto = [normalize_sql(sql) for sql, _ in conexion.executed[1:]]
    assert not any("FOR UPDATE" in sql for sql in resto)
    assert any(sql.startswith("SELECT id_rol, id_area, nombres, email, estado FROM usuario") for sql in resto)


def test_ninguna_otra_ruta_escribe_el_rol_o_el_estado_de_usuarios():
    """Si aparece otra escritura sobre usuario.id_rol o usuario.estado, debe
    pasar por la misma regla. Se revisa todo el backend."""
    from pathlib import Path

    raiz = Path(usuarios_routes.__file__).resolve().parents[1]
    escrituras = []
    for archivo in raiz.rglob("*.py"):
        texto = archivo.read_text(encoding="utf-8")
        for coincidencia in re.finditer(r"(UPDATE|DELETE FROM)\s+usuario\b(.*?)(?:\"\"\"|\"|')", texto, re.S):
            cuerpo = coincidencia.group(2)
            if coincidencia.group(1) == "DELETE FROM" or re.search(r"\b(id_rol|estado)\s*=", cuerpo):
                escrituras.append(archivo.name)
    assert sorted(escrituras) == ["usuarios_routes.py"] * 3
