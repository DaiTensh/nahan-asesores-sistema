# -*- coding: utf-8 -*-
"""RF30 — Historial de accesos y modificaciones de usuarios.

Criterios (Documento 0, Tabla 7.30): registra cada inicio y cierre de sesión,
registra las acciones relevantes sobre usuarios, lo consulta el administrador,
se filtra por usuario, fecha y acción, y los registros no se pueden
modificar ni eliminar.

Corre sobre SQLite en memoria con las rutas reales. El evento se guarda con
registrar_auditoria() en la tabla AUDITORIA, la misma de RF56 y RF40.
"""
import hashlib
import re
import sqlite3
import time
from pathlib import Path

import pytest

import backend.routes.auth_routes as auth_routes
import backend.routes.historial_routes as historial_routes
import backend.routes.reportes_routes as reportes_routes
import backend.routes.usuarios_routes as usuarios_routes
import backend.utils.auth as auth_utils
from backend.app import app as flask_app

RAIZ = Path(__file__).resolve().parents[1]

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
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tabla_afectada TEXT, id_registro INTEGER, accion TEXT, datos_anteriores TEXT,
    datos_nuevos TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_JURIDICA'), ('USUARIO_AREA_CONTABLE');
INSERT INTO area (nombre_area) VALUES ('JURIDICA'), ('CONTABLE'), ('ADMINISTRACION');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) VALUES
 (1, 3, 'Admin Nahan', 'admin@nahan.local', 'x', 'ACTIVO'),
 (2, 1, 'Usuaria Juridica', 'juridica@nahan.local', 'x', 'ACTIVO'),
 (3, 2, 'Usuario Contable', 'contable@nahan.local', 'x', 'INACTIVO');
"""

CLAVE = "clave-de-prueba-2026"


def _traducir(sql):
    sql = sql.replace("%s", "?")
    sql = sql.replace("DATE_ADD(NOW(), INTERVAL ? MINUTE)", "datetime('now', '+' || ? || ' minutes')")
    sql = re.sub(r"\bNOW\(\)", "datetime('now')", sql)
    return sql.replace("TRUE", "1").replace("FALSE", "0")


class _Cursor:
    def __init__(self, conexion, dictionary):
        self._cursor = conexion.cursor()
        self._dictionary = dictionary
        self.lastrowid = None
        self.rowcount = 0

    def _fila(self, fila):
        if fila is None:
            return None
        return dict(fila) if self._dictionary else tuple(fila)

    def execute(self, sql, params=()):
        self._cursor.execute(_traducir(sql), tuple(params))
        self.lastrowid = self._cursor.lastrowid
        self.rowcount = self._cursor.rowcount

    def executemany(self, sql, secuencia):
        self._cursor.executemany(_traducir(sql), [tuple(p) for p in secuencia])

    def fetchone(self):
        return self._fila(self._cursor.fetchone())

    def fetchall(self):
        return [self._fila(fila) for fila in self._cursor.fetchall()]

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _Conexion:
    def __init__(self, sqlite_conexion):
        self._conexion = sqlite_conexion

    def cursor(self, dictionary=False):
        return _Cursor(self._conexion, dictionary)

    def commit(self):
        self._conexion.commit()

    def rollback(self):
        self._conexion.rollback()

    def close(self):
        pass


@pytest.fixture
def base():
    from backend.utils.security import hash_password

    conexion = sqlite3.connect(":memory:")
    conexion.row_factory = sqlite3.Row
    conexion.executescript(ESQUEMA)
    conexion.execute("UPDATE usuario SET password_hash = ?", (hash_password(CLAVE),))
    conexion.commit()
    yield conexion
    conexion.close()


@pytest.fixture
def cliente(base, monkeypatch):
    abrir = lambda: _Conexion(base)
    for modulo in (auth_routes, auth_utils, usuarios_routes, historial_routes, reportes_routes):
        monkeypatch.setattr(modulo, "get_connection", abrir)
    monkeypatch.setattr(auth_utils, "obtener_config_sesion", lambda: (30, 60))
    monkeypatch.setattr(auth_routes, "enviar_correo", lambda *args, **kwargs: False)
    monkeypatch.setenv("APP_URL_FRONTEND", "http://127.0.0.1:5500/frontend")

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as cliente_http:
        yield cliente_http


def _login(cliente, email="admin@nahan.local", clave=CLAVE):
    return cliente.post("/api/login", json={"email": email, "password": clave})


def _eventos(base, accion=None):
    consulta = "SELECT * FROM auditoria"
    parametros = ()
    if accion:
        consulta += " WHERE accion = ?"
        parametros = (accion,)
    return [dict(fila) for fila in base.execute(consulta + " ORDER BY id_auditoria", parametros).fetchall()]


def _texto_auditado(base):
    return " ".join(
        f"{fila['datos_anteriores'] or ''} {fila['datos_nuevos'] or ''}" for fila in _eventos(base)
    )


# --- C1: inicio y cierre de sesión ---

def test_el_inicio_de_sesion_queda_registrado(cliente, base):
    respuesta = _login(cliente, "juridica@nahan.local")

    assert respuesta.status_code == 200
    (evento,) = _eventos(base, "LOGIN")
    assert evento["id_usuario"] == 2
    assert evento["tabla_afectada"] == "sesion"
    assert evento["id_registro"] == 2
    assert evento["fecha"]
    assert CLAVE not in _texto_auditado(base)


@pytest.mark.parametrize("email, clave", [
    ("juridica@nahan.local", "clave-incorrecta"),
    ("nadie@nahan.local", CLAVE),
    ("contable@nahan.local", CLAVE),  # cuenta inactiva
])
def test_un_inicio_de_sesion_fallido_no_deja_un_login(cliente, base, email, clave):
    respuesta = _login(cliente, email, clave)

    assert respuesta.status_code in (401, 403)
    assert _eventos(base) == []
    with cliente.session_transaction() as sesion:
        assert "usuario_id" not in sesion


def test_si_no_se_puede_auditar_el_login_no_se_abre_la_sesion(cliente, base, monkeypatch):
    def fallar(*args, **kwargs):
        raise RuntimeError("auditoria caida")

    monkeypatch.setattr(auth_routes, "registrar_auditoria", fallar)

    assert _login(cliente).status_code == 500
    with cliente.session_transaction() as sesion:
        assert "usuario_id" not in sesion


def test_el_cierre_de_sesion_conserva_al_usuario_real(cliente, base):
    _login(cliente, "juridica@nahan.local")

    respuesta = cliente.post("/api/logout")

    assert respuesta.status_code == 200
    (evento,) = _eventos(base, "LOGOUT")
    assert evento["id_usuario"] == 2
    assert evento["tabla_afectada"] == "sesion"
    assert evento["id_registro"] == 2
    with cliente.session_transaction() as sesion:
        assert "usuario_id" not in sesion


def test_logout_sin_sesion_responde_bien_y_no_inventa_actor(cliente, base):
    respuesta = cliente.post("/api/logout")

    assert respuesta.status_code == 200
    assert _eventos(base) == []


def test_un_fallo_al_auditar_no_impide_cerrar_la_sesion(cliente, base, monkeypatch):
    _login(cliente)

    def fallar(*args, **kwargs):
        raise RuntimeError("auditoria caida")

    monkeypatch.setattr(auth_routes, "registrar_auditoria", fallar)

    assert cliente.post("/api/logout").status_code == 200
    with cliente.session_transaction() as sesion:
        assert "usuario_id" not in sesion


def test_el_cierre_por_inactividad_sigue_siendo_un_evento_distinto(cliente, base):
    _login(cliente)
    with cliente.session_transaction() as sesion:
        sesion["ultima_actividad"] = time.time() - 31 * 60

    assert cliente.get("/api/auth/me").status_code == 401

    acciones = [evento["accion"] for evento in _eventos(base)]
    assert acciones == ["LOGIN", "CIERRE_INACTIVIDAD"]


# --- C2: acciones sobre usuarios ---

def _alta(cliente, **cambios):
    cuerpo = {"id_rol": 2, "id_area": 1, "nombres": "Persona Nueva",
              "email": "nueva@nahan.local", "password": "ClaveTemporal-123"}
    cuerpo.update(cambios)
    return cliente.post("/api/usuarios", json=cuerpo)


def test_crear_un_usuario_queda_registrado_sin_credenciales(cliente, base):
    _login(cliente)

    respuesta = _alta(cliente)

    assert respuesta.status_code == 201
    (evento,) = _eventos(base, "USUARIO_CREADO")
    nuevo = base.execute("SELECT id_usuario, password_hash FROM usuario WHERE email = 'nueva@nahan.local'").fetchone()
    assert evento["id_usuario"] == 1
    assert evento["tabla_afectada"] == "usuario"
    assert evento["id_registro"] == nuevo["id_usuario"]
    assert "email=nueva@nahan.local" in evento["datos_nuevos"]
    texto = _texto_auditado(base)
    assert "ClaveTemporal-123" not in texto
    assert nuevo["password_hash"] not in texto
    assert "password" not in texto.lower()


def test_modificar_un_usuario_guarda_el_antes_y_el_despues(cliente, base):
    _login(cliente)

    respuesta = cliente.put("/api/usuarios/2", json={
        "id_rol": 2, "id_area": 1, "nombres": "Usuaria Renombrada",
        "email": "juridica@nahan.local", "estado": "ACTIVO"})

    assert respuesta.status_code == 200
    (evento,) = _eventos(base, "USUARIO_MODIFICADO")
    assert evento["id_usuario"] == 1
    assert evento["id_registro"] == 2
    assert "nombres=Usuaria Juridica" in evento["datos_anteriores"]
    assert "nombres=Usuaria Renombrada" in evento["datos_nuevos"]
    assert "password" not in _texto_auditado(base).lower()


def test_una_modificacion_sin_cambios_no_deja_evento(cliente, base):
    _login(cliente)

    respuesta = cliente.put("/api/usuarios/2", json={
        "id_rol": 2, "id_area": 1, "nombres": "Usuaria Juridica",
        "email": "juridica@nahan.local", "estado": "ACTIVO"})

    assert respuesta.status_code == 200
    assert _eventos(base, "USUARIO_MODIFICADO") == []


def test_desactivar_un_usuario_queda_registrado(cliente, base):
    _login(cliente)

    respuesta = cliente.put("/api/usuarios/2/desactivar")

    assert respuesta.status_code == 200
    (evento,) = _eventos(base, "USUARIO_DESACTIVADO")
    assert (evento["id_usuario"], evento["id_registro"]) == (1, 2)
    assert evento["datos_anteriores"] == "estado=ACTIVO"
    assert evento["datos_nuevos"] == "estado=INACTIVO"


def test_desactivar_un_usuario_ya_inactivo_no_deja_evento(cliente, base):
    _login(cliente)

    assert cliente.put("/api/usuarios/3/desactivar").status_code == 200
    assert _eventos(base, "USUARIO_DESACTIVADO") == []


def test_cambiar_el_rol_queda_registrado(cliente, base):
    _login(cliente)

    respuesta = cliente.put("/api/usuarios/2/rol", json={"id_rol": 3})

    assert respuesta.status_code == 200
    (evento,) = _eventos(base, "ROL_USUARIO_MODIFICADO")
    assert (evento["id_usuario"], evento["id_registro"]) == (1, 2)
    assert evento["datos_anteriores"] == "id_rol=2, id_area=1"
    assert evento["datos_nuevos"] == "id_rol=3, id_area=2"


def test_operaciones_sobre_un_usuario_inexistente_responden_404_sin_evento(cliente, base):
    _login(cliente)

    assert cliente.put("/api/usuarios/99", json={
        "id_rol": 2, "id_area": 1, "nombres": "X", "email": "x@x.cl", "estado": "ACTIVO"}).status_code == 404
    assert cliente.put("/api/usuarios/99/desactivar").status_code == 404
    assert cliente.put("/api/usuarios/99/rol", json={"id_rol": 3}).status_code == 404

    assert [e["accion"] for e in _eventos(base)] == ["LOGIN"]


def test_una_operacion_rechazada_no_deja_un_evento_de_exito(cliente, base):
    _login(cliente)

    assert _alta(cliente, id_rol=2, id_area=2).status_code == 422   # rol y área incoherentes
    assert _alta(cliente, email="").status_code == 400              # falta un dato
    assert _alta(cliente, email="juridica@nahan.local").status_code == 500  # correo duplicado

    assert _eventos(base, "USUARIO_CREADO") == []
    assert base.execute("SELECT COUNT(*) FROM usuario").fetchone()[0] == 3


def test_el_evento_y_la_operacion_son_atomicos(cliente, base, monkeypatch):
    _login(cliente)

    def fallar(*args, **kwargs):
        raise RuntimeError("auditoria caida")

    monkeypatch.setattr(usuarios_routes, "registrar_auditoria", fallar)

    assert _alta(cliente).status_code == 500
    assert base.execute("SELECT COUNT(*) FROM usuario").fetchone()[0] == 3

    assert cliente.put("/api/usuarios/2/desactivar").status_code == 500
    assert base.execute("SELECT estado FROM usuario WHERE id_usuario = 2").fetchone()[0] == "ACTIVO"


def test_un_usuario_no_administrador_no_puede_operar_ni_deja_evento(cliente, base):
    _login(cliente, "juridica@nahan.local")

    assert _alta(cliente).status_code == 403
    assert cliente.put("/api/usuarios/3/desactivar").status_code == 403
    assert cliente.put("/api/usuarios/3/rol", json={"id_rol": 2}).status_code == 403

    assert [e["accion"] for e in _eventos(base)] == ["LOGIN"]


def _solicitar_enlace(base, id_usuario, token="token-secreto-de-prueba"):
    base.execute(
        "INSERT INTO token_recuperacion (id_usuario, token_hash, fecha_expiracion) "
        "VALUES (?, ?, datetime('now', '+60 minutes'))",
        (id_usuario, hashlib.sha256(token.encode()).hexdigest()),
    )
    base.commit()
    return token


def test_restablecer_la_contrasena_solo_deja_constancia_de_que_ocurrio(cliente, base):
    token = _solicitar_enlace(base, 2)
    anterior = base.execute("SELECT password_hash FROM usuario WHERE id_usuario = 2").fetchone()[0]

    respuesta = cliente.post("/api/auth/restablecer", json={"token": token, "password": "otra-clave-2026"})

    assert respuesta.status_code == 200
    nuevo = base.execute("SELECT password_hash FROM usuario WHERE id_usuario = 2").fetchone()[0]
    (evento,) = _eventos(base, "CONTRASENA_RESTABLECIDA")
    assert (evento["id_usuario"], evento["id_registro"], evento["tabla_afectada"]) == (2, 2, "usuario")
    texto = _texto_auditado(base)
    for secreto in ("otra-clave-2026", CLAVE, anterior, nuevo, token):
        assert secreto not in texto
    assert evento["datos_anteriores"] is None


def test_un_restablecimiento_con_enlace_invalido_no_deja_evento(cliente, base):
    respuesta = cliente.post("/api/auth/restablecer", json={"token": "no-existe", "password": "otra-clave-2026"})

    assert respuesta.status_code == 400
    assert _eventos(base) == []


# --- C3 y C4: consulta del administrador y filtros ---

def _poblar(base):
    filas = [
        (1, "sesion", 1, "LOGIN", "2026-09-01 08:00:00"),
        (2, "sesion", 2, "LOGIN", "2026-09-02 09:00:00"),
        (2, "sesion", 2, "LOGOUT", "2026-09-02 18:00:00"),
        (1, "usuario", 3, "USUARIO_CREADO", "2026-09-03 10:00:00"),
        (1, "usuario", 3, "USUARIO_DESACTIVADO", "2026-09-10 10:00:00"),
    ]
    base.executemany(
        "INSERT INTO auditoria (id_usuario, tabla_afectada, id_registro, accion, fecha) VALUES (?, ?, ?, ?, ?)",
        filas,
    )
    base.commit()


def _historial(cliente, consulta=""):
    respuesta = cliente.get(f"/api/historial?{consulta}")
    assert respuesta.status_code == 200, respuesta.get_json()
    return respuesta.get_json()["eventos"]


def test_el_administrador_consulta_y_otro_rol_es_rechazado(cliente, base):
    _poblar(base)
    _login(cliente, "juridica@nahan.local")
    assert cliente.get("/api/historial").status_code == 403
    assert cliente.get("/api/historial/filtros").status_code == 403
    cliente.post("/api/logout")

    _login(cliente)
    assert len(_historial(cliente)) >= 5


def test_sin_sesion_el_historial_responde_401(cliente):
    assert cliente.get("/api/historial").status_code == 401


def test_el_historial_muestra_sesion_y_usuarios_con_su_modulo(cliente, base):
    _poblar(base)
    _login(cliente)

    modulos = {(e["accion"], e["modulo"]) for e in _historial(cliente)}

    assert ("LOGIN", "Seguridad") in modulos
    assert ("USUARIO_CREADO", "Usuarios") in modulos


def test_filtro_por_usuario(cliente, base):
    _poblar(base)
    _login(cliente)

    eventos = _historial(cliente, "id_usuario=2")

    assert {e["accion"] for e in eventos} == {"LOGIN", "LOGOUT"}
    assert {e["id_usuario"] for e in eventos} == {2}


def test_filtro_por_fecha(cliente, base):
    _poblar(base)
    _login(cliente)

    eventos = _historial(cliente, "fecha_inicio=2026-09-02&fecha_fin=2026-09-03")

    assert {e["accion"] for e in eventos} == {"LOGIN", "LOGOUT", "USUARIO_CREADO"}
    assert all("2026-09-02" <= e["fecha"][:10] <= "2026-09-03" for e in eventos)


def test_filtro_por_accion(cliente, base):
    _poblar(base)
    _login(cliente)

    eventos = _historial(cliente, "accion=LOGIN")

    assert {e["accion"] for e in eventos} == {"LOGIN"}
    assert len(eventos) == 3  # dos sembrados y el del propio inicio de sesión del administrador


def test_los_filtros_se_combinan(cliente, base):
    _poblar(base)
    _login(cliente)

    eventos = _historial(cliente, "id_usuario=1&accion=USUARIO_DESACTIVADO&fecha_inicio=2026-09-01&fecha_fin=2026-09-30")
    assert [(e["accion"], e["id_usuario"]) for e in eventos] == [("USUARIO_DESACTIVADO", 1)]

    assert _historial(cliente, "id_usuario=2&accion=USUARIO_CREADO") == []
    assert _historial(cliente, "accion=USUARIO_DESACTIVADO&fecha_inicio=2026-09-01&fecha_fin=2026-09-05") == []
    assert _historial(cliente, "modulo=Usuarios&accion=LOGIN") == []


def test_una_accion_desconocida_devuelve_lista_vacia_y_una_malformada_400(cliente, base):
    _poblar(base)
    _login(cliente)

    assert _historial(cliente, "accion=NO_EXISTE") == []
    for malo in ("login", "LOGIN' OR '1'='1", "A B", "X" * 51):
        assert cliente.get("/api/historial", query_string={"accion": malo}).status_code == 400


def test_el_filtro_por_accion_no_es_inyectable(cliente, base):
    _poblar(base)
    _login(cliente)

    respuesta = cliente.get("/api/historial", query_string={"accion": "LOGIN'; DELETE FROM auditoria; --"})

    assert respuesta.status_code == 400
    assert base.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] >= 6


def test_las_opciones_de_filtro_incluyen_solo_las_acciones_existentes(cliente, base):
    _poblar(base)
    _login(cliente)

    datos = cliente.get("/api/historial/filtros").get_json()

    assert datos["acciones"] == ["LOGIN", "LOGOUT", "USUARIO_CREADO", "USUARIO_DESACTIVADO"]
    assert {u["nombres"] for u in datos["usuarios"]} >= {"Admin Nahan", "Usuaria Juridica"}


def test_el_historial_esta_en_orden_cronologico_descendente(cliente, base):
    _poblar(base)
    _login(cliente)

    fechas = [e["fecha"] for e in _historial(cliente)]

    assert fechas == sorted(fechas, reverse=True)


def test_el_historial_consolidado_rf40_recibe_los_eventos_de_rf30(cliente, base, monkeypatch):
    monkeypatch.setattr(
        reportes_routes, "_registrar_generacion",
        lambda *args, **kwargs: {"id_reporte": 1, "fecha_generacion": "2026-09-30 10:00"},
    )
    _poblar(base)
    _login(cliente)

    respuesta = cliente.get("/api/reportes/historial-consolidado?fecha_inicio=2000-01-01&fecha_fin=2999-12-31")

    assert respuesta.status_code == 200
    assert {"LOGIN", "LOGOUT", "USUARIO_CREADO"} <= {e["accion"] for e in respuesta.get_json()["eventos"]}


# --- C5: inmutabilidad ---

def test_la_api_no_permite_modificar_ni_eliminar_el_historial(cliente, base):
    _poblar(base)
    _login(cliente)
    total = base.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0]

    for metodo in ("post", "put", "patch", "delete"):
        for ruta in ("/api/historial", "/api/historial/1", "/api/auditoria", "/api/auditoria/1"):
            respuesta = getattr(cliente, metodo)(ruta, json={"accion": "X"})
            assert respuesta.status_code in (404, 405), (metodo, ruta, respuesta.status_code)

    assert base.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == total


def test_ninguna_ruta_expone_escritura_sobre_el_historial():
    for regla in flask_app.url_map.iter_rules():
        if "historial" in regla.rule or "auditoria" in regla.rule:
            assert regla.methods - {"GET", "HEAD", "OPTIONS"} == set(), regla.rule


def test_el_codigo_nunca_actualiza_ni_borra_auditoria():
    for archivo in (RAIZ / "backend").rglob("*.py"):
        texto = re.sub(r"\s+", " ", archivo.read_text(encoding="utf-8")).upper()
        assert "UPDATE AUDITORIA" not in texto, archivo
        assert "DELETE FROM AUDITORIA" not in texto, archivo
        assert "TRUNCATE TABLE AUDITORIA" not in texto, archivo


def test_ninguna_ruta_inserta_en_auditoria_a_mano():
    for modulo in ("auth_routes", "usuarios_routes", "historial_routes"):
        assert "INSERT INTO auditoria" not in (RAIZ / "backend" / "routes" / f"{modulo}.py").read_text(encoding="utf-8")


# --- Frontend ---

def test_la_vista_del_historial_ofrece_el_filtro_por_accion():
    html = (RAIZ / "frontend" / "historial" / "historial.html").read_text(encoding="utf-8")
    js = (RAIZ / "frontend" / "historial" / "historial.js").read_text(encoding="utf-8")

    assert 'id="selectAccion"' in html
    assert 'parametros.set("accion", accion)' in js
    assert "data.acciones" in js
    assert "protegerPagina([\"ADMINISTRADOR\"])" in html
    assert "innerHTML" not in js
