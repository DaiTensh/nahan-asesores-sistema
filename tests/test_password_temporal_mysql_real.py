# -*- coding: utf-8 -*-
"""Contraseña temporal con cambio obligatorio (migración 014) contra MySQL real desechable.

Usa la autenticación REAL (login con bcrypt, sesión firmada, estado leído de la base en cada solicitud), no la
fila simulada de `iniciar_sesion`. Datos ficticios; nunca el puerto 3306.
"""
import datetime
import hashlib
import os
import re
import threading

import pytest

import backend.utils.auth as auth_module
from backend.app import app as flask_app
from backend.config.db import get_connection as conexion_real
from backend.utils.security import hash_password
from tests.mysql_desechable import (
    BASE_APP, CLAVE_APP, USUARIO_APP, MySQLDesechable, herramientas_disponibles, sembrar_datos_ficticios,
)

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)

CLAVE_ADMIN = "Admin-Personal-1"
CLAVE_JURIDICA = "Juridica-Personal-1"
NUEVA = "Nueva-Personal-Segura-9"


@pytest.fixture(scope="module")
def servidor():
    s = MySQLDesechable().iniciar()
    yield s
    s.detener()


@pytest.fixture
def mundo(servidor, monkeypatch):
    root = servidor.conectar()
    c = root.cursor()
    c.execute(f"DROP DATABASE IF EXISTS {BASE_APP}")
    c.execute(f"CREATE DATABASE {BASE_APP} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    root.close()
    servidor.cargar_esquema()
    cn = servidor.conectar(base=BASE_APP)
    sembrar_datos_ficticios(cn)
    cur = cn.cursor()
    # Cuentas «existentes» (anteriores a la migración 014): contraseña personal, sin cambio pendiente.
    cur.execute("UPDATE usuario SET password_hash = %s WHERE id_usuario = 1", (hash_password(CLAVE_ADMIN),))
    cur.execute("UPDATE usuario SET password_hash = %s WHERE id_usuario = 2", (hash_password(CLAVE_JURIDICA),))
    cn.commit()
    cn.close()
    assert servidor.puerto != 3306
    for k, v in {"DB_HOST": "127.0.0.1", "DB_PORT": str(servidor.puerto), "DB_USER": USUARIO_APP,
                 "DB_PASSWORD": CLAVE_APP, "DB_NAME": BASE_APP}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(auth_module, "get_connection", conexion_real)  # autenticación real, no la simulada

    class Mundo:
        def sql(self, sentencia, parametros=None, filas=False):
            conexion = servidor.conectar(base=BASE_APP)
            cur = conexion.cursor(dictionary=True)
            cur.execute(sentencia, parametros)
            resultado = cur.fetchall() if filas else None
            conexion.commit()
            conexion.close()
            return resultado

        def usuario(self, email):
            return self.sql("SELECT * FROM usuario WHERE email = %s", (email,), filas=True)[0]

    return Mundo()


def _cliente():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


def _entrar(email, clave):
    c = _cliente()
    r = c.post("/api/login", json={"email": email, "password": clave})
    return c, r


def _admin():
    c, r = _entrar("admin@ejemplo.invalid", CLAVE_ADMIN)
    assert r.status_code == 200, r.get_json()
    return c


def _crear(admin, email="nueva@ejemplo.invalid", **extra):
    r = admin.post("/api/usuarios", json={"nombres": "Persona Nueva", "email": email, "id_rol": 2, "id_area": 1, **extra})
    assert r.status_code == 201, r.get_json()
    return r


def _auditoria(mundo, accion=None):
    if accion:
        return mundo.sql("SELECT * FROM auditoria WHERE accion = %s ORDER BY id_auditoria", (accion,), filas=True)
    return mundo.sql("SELECT * FROM auditoria ORDER BY id_auditoria", filas=True)


# ------------------------------------------------------------------ migración y datos existentes
def test_los_usuarios_existentes_conservan_su_comportamiento(mundo):
    for email in ("admin@ejemplo.invalid", "juridica@ejemplo.invalid"):
        fila = mundo.usuario(email)
        assert (fila["debe_cambiar_password"], fila["version_credenciales"]) == (0, 0)
    c, r = _entrar("juridica@ejemplo.invalid", CLAVE_JURIDICA)
    assert r.status_code == 200 and r.get_json()["usuario"]["debe_cambiar_password"] is False
    assert c.get("/api/clientes/listado").status_code == 200
    me = c.get("/api/auth/me").get_json()
    assert me["debe_cambiar_password"] is False
    assert set(me["usuario"]) == {"id_usuario", "nombres", "id_rol", "nombre_rol", "id_area"}, "el contrato de /auth/me no cambia"


# ------------------------------------------------------------------ creación con contraseña temporal
def test_el_administrador_crea_una_cuenta_con_contrasena_temporal_aleatoria(mundo):
    admin = _admin()
    r = _crear(admin)
    cuerpo = r.get_json()
    temporal = cuerpo["password_temporal"]
    assert cuerpo["debe_cambiar_password"] is True and r.headers["Cache-Control"] == "no-store"
    assert len(temporal) == 14 and re.search(r"[A-Z]", temporal) and re.search(r"[a-z]", temporal) and re.search(r"\d", temporal)
    fila = mundo.usuario("nueva@ejemplo.invalid")
    assert fila["debe_cambiar_password"] == 1 and fila["version_credenciales"] == 0
    assert fila["password_hash"].startswith("$2") and temporal not in fila["password_hash"], "solo se guarda el hash"


def test_las_temporales_son_distintas_y_no_aparecen_en_listados_ni_auditoria(mundo):
    admin = _admin()
    t1 = _crear(admin, "uno@ejemplo.invalid").get_json()["password_temporal"]
    t2 = _crear(admin, "dos@ejemplo.invalid").get_json()["password_temporal"]
    assert t1 != t2
    listado = admin.get("/api/usuarios")
    texto = listado.get_data(as_text=True)
    assert "password" not in texto.lower().replace("debe_cambiar_password", "") and "$2" not in texto
    assert t1 not in texto and t2 not in texto
    pendientes = {u["email"]: u["debe_cambiar_password"] for u in listado.get_json()}
    assert pendientes["uno@ejemplo.invalid"] is True and pendientes["admin@ejemplo.invalid"] is False
    detalle = admin.get("/api/usuarios/%d" % mundo.usuario("uno@ejemplo.invalid")["id_usuario"]).get_data(as_text=True)
    assert t1 not in detalle and "$2" not in detalle
    for fila in _auditoria(mundo):
        for campo in ("datos_anteriores", "datos_nuevos"):
            assert t1 not in (fila[campo] or "") and t2 not in (fila[campo] or "")
            assert "$2" not in (fila[campo] or "")
    creada = _auditoria(mundo, "USUARIO_CREADO")[-1]
    assert "contraseña temporal con cambio obligatorio" in creada["datos_nuevos"]


def test_una_contrasena_indicada_por_el_administrador_tambien_es_temporal(mundo):
    admin = _admin()
    r = _crear(admin, password="Indicada-Por-Admin-1")
    assert "password_temporal" not in r.get_json() and r.get_json()["debe_cambiar_password"] is True
    assert mundo.usuario("nueva@ejemplo.invalid")["debe_cambiar_password"] == 1
    corta = admin.post("/api/usuarios", json={"nombres": "X", "email": "x@ejemplo.invalid", "id_rol": 2, "id_area": 1, "password": "corta"})
    assert corta.status_code == 400


def test_solo_el_administrador_crea_y_restablece(mundo):
    _crear(_admin())
    c, _ = _entrar("juridica@ejemplo.invalid", CLAVE_JURIDICA)
    assert c.post("/api/usuarios", json={"nombres": "X", "email": "x@ejemplo.invalid", "id_rol": 2, "id_area": 1}).status_code == 403
    destino = mundo.usuario("nueva@ejemplo.invalid")["id_usuario"]
    assert c.post(f"/api/usuarios/{destino}/restablecer-password", json={"confirmar": True}).status_code == 403
    assert mundo.usuario("nueva@ejemplo.invalid")["version_credenciales"] == 0
    anonimo = _cliente()
    assert anonimo.post(f"/api/usuarios/{destino}/restablecer-password", json={"confirmar": True}).status_code == 401


# ------------------------------------------------------------------ primer inicio: bloqueo en el servidor
def _temporal(mundo, email="nueva@ejemplo.invalid"):
    t = _crear(_admin(), email).get_json()["password_temporal"]
    return t


def test_con_la_temporal_el_login_funciona_pero_el_servidor_bloquea_todo_lo_demas(mundo):
    temporal = _temporal(mundo)
    c, r = _entrar("nueva@ejemplo.invalid", temporal)
    assert r.status_code == 200 and r.get_json()["usuario"]["debe_cambiar_password"] is True
    me = c.get("/api/auth/me")
    assert me.status_code == 200 and me.get_json()["debe_cambiar_password"] is True
    permitidas = {"/api/auth/me", "/api/auth/sesion", "/api/auth/sesion/extender", "/api/auth/cambiar-password", "/api/logout"}
    publicas = {"/api/login", "/api/auth/recuperar", "/api/auth/recuperar/verificar", "/api/auth/restablecer"}
    bloqueos = []
    for regla in flask_app.url_map.iter_rules():
        if not regla.rule.startswith("/api/") or regla.rule in permitidas | publicas:
            continue
        ruta = re.sub(r"<(?:int:)?[^>]+>", "1", regla.rule)
        for metodo in sorted(regla.methods - {"OPTIONS", "HEAD"}):
            r = c.open(ruta, method=metodo, json={} if metodo != "GET" else None)
            if r.status_code not in (403, 401) or (r.get_json() or {}).get("codigo") not in ("CAMBIO_PASSWORD_OBLIGATORIO", None):
                bloqueos.append((metodo, ruta, r.status_code))
            if r.status_code == 403 and (r.get_json() or {}).get("codigo") != "CAMBIO_PASSWORD_OBLIGATORIO":
                # Rutas exclusivas del administrador: el rol se evalúa antes y también rechaza (403 de permisos).
                assert (r.get_json() or {}).get("error") == "No tiene permisos para acceder a este recurso", (metodo, ruta)
    assert bloqueos == []
    # Las rutas operativas responden con el código específico
    r = c.get("/api/clientes/listado")
    assert r.status_code == 403 and r.get_json()["codigo"] == "CAMBIO_PASSWORD_OBLIGATORIO"
    assert c.post("/api/control-horas/iniciar", json={"id_tarea": 1}).get_json()["codigo"] == "CAMBIO_PASSWORD_OBLIGATORIO"
    assert c.get("/api/auth/sesion").status_code == 200
    assert c.post("/api/logout").status_code == 200


def test_validaciones_del_cambio(mundo):
    temporal = _temporal(mundo)
    c, _ = _entrar("nueva@ejemplo.invalid", temporal)
    enviar = lambda **k: c.post("/api/auth/cambiar-password", json=k)
    base = {"password_actual": temporal, "password_nueva": NUEVA, "confirmacion": NUEVA}
    assert enviar().status_code == 400
    assert enviar(**{**base, "password_nueva": "corta1", "confirmacion": "corta1"}).status_code == 400
    assert enviar(**{**base, "confirmacion": "Otra-Distinta-9"}).status_code == 400
    assert enviar(**{**base, "password_nueva": temporal, "confirmacion": temporal}).status_code == 400, "no se reutiliza la temporal"
    assert enviar(**{**base, "password_nueva": "ñ" * 40, "confirmacion": "ñ" * 40}).status_code == 400, "más de 72 bytes"
    assert enviar(**{**base, "password_actual": "Equivocada-1"}).status_code == 400
    assert enviar(**{**base, "password_nueva": 12345678}).status_code == 400
    fila = mundo.usuario("nueva@ejemplo.invalid")
    assert fila["debe_cambiar_password"] == 1 and fila["version_credenciales"] == 0, "nada cambió"
    assert c.get("/api/clientes/listado").status_code == 403


def test_cambio_correcto_quita_la_obligacion_renueva_la_sesion_e_invalida_la_temporal(mundo):
    temporal = _temporal(mundo)
    c, _ = _entrar("nueva@ejemplo.invalid", temporal)
    antes = mundo.usuario("nueva@ejemplo.invalid")["password_hash"]
    r = c.post("/api/auth/cambiar-password", json={"password_actual": temporal, "password_nueva": NUEVA, "confirmacion": NUEVA})
    assert r.status_code == 200 and r.get_json()["debe_cambiar_password"] is False
    fila = mundo.usuario("nueva@ejemplo.invalid")
    assert (fila["debe_cambiar_password"], fila["version_credenciales"]) == (0, 1)
    assert fila["password_hash"] != antes and fila["password_hash"].startswith("$2") and NUEVA not in fila["password_hash"]
    assert c.get("/api/clientes/listado").status_code == 200, "la sesión renovada ya sirve"
    assert c.get("/api/auth/me").get_json()["debe_cambiar_password"] is False
    # la temporal dejó de funcionar y la nueva funciona
    assert _entrar("nueva@ejemplo.invalid", temporal)[1].status_code == 401
    assert _entrar("nueva@ejemplo.invalid", NUEVA)[1].status_code == 200
    evento = _auditoria(mundo, "CONTRASENA_CAMBIADA")
    assert len(evento) == 1 and evento[0]["id_usuario"] == fila["id_usuario"]
    for fila_aud in _auditoria(mundo):
        for campo in ("datos_anteriores", "datos_nuevos"):
            assert temporal not in (fila_aud[campo] or "") and NUEVA not in (fila_aud[campo] or "")
            assert "$2" not in (fila_aud[campo] or "")


def test_el_cambio_invalida_las_otras_sesiones_de_la_cuenta(mundo):
    temporal = _temporal(mundo)
    a, _ = _entrar("nueva@ejemplo.invalid", temporal)
    b, _ = _entrar("nueva@ejemplo.invalid", temporal)
    assert a.post("/api/auth/cambiar-password", json={"password_actual": temporal, "password_nueva": NUEVA, "confirmacion": NUEVA}).status_code == 200
    assert b.get("/api/auth/me").status_code == 401, "la otra sesión (con la temporal) quedó invalidada"
    assert a.get("/api/auth/me").status_code == 200


def test_dos_cambios_simultaneos_con_la_misma_temporal_solo_aplican_uno(mundo):
    temporal = _temporal(mundo)
    resultados = []

    def lanzar(i):
        c, _ = _entrar("nueva@ejemplo.invalid", temporal)
        nueva = f"Concurrente-Personal-{i}0"
        resultados.append(c.post("/api/auth/cambiar-password", json={"password_actual": temporal, "password_nueva": nueva, "confirmacion": nueva}).status_code)

    hilos = [threading.Thread(target=lanzar, args=(i,)) for i in range(4)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert resultados.count(200) == 1, resultados
    assert mundo.usuario("nueva@ejemplo.invalid")["version_credenciales"] == 1
    assert len(_auditoria(mundo, "CONTRASENA_CAMBIADA")) == 1


def test_los_intentos_con_contrasena_actual_equivocada_comparten_el_limite_de_login(mundo):
    temporal = _temporal(mundo)
    c, _ = _entrar("nueva@ejemplo.invalid", temporal)
    codigos = []
    for _ in range(25):
        r = c.post("/api/auth/cambiar-password", json={"password_actual": "Equivocada-1", "password_nueva": NUEVA, "confirmacion": NUEVA})
        codigos.append(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in codigos, "el límite de intentos existente también protege este endpoint"


# ------------------------------------------------------------------ restablecimiento por el administrador
def test_restablecer_invalida_contrasena_y_sesiones_y_obliga_a_cambiar(mundo):
    admin = _admin()
    persona, r = _entrar("juridica@ejemplo.invalid", CLAVE_JURIDICA)
    assert persona.get("/api/clientes/listado").status_code == 200
    destino = mundo.usuario("juridica@ejemplo.invalid")["id_usuario"]

    sin_confirmar = admin.post(f"/api/usuarios/{destino}/restablecer-password", json={})
    assert sin_confirmar.status_code == 400 and mundo.usuario("juridica@ejemplo.invalid")["version_credenciales"] == 0
    r = admin.post(f"/api/usuarios/{destino}/restablecer-password", json={"confirmar": True})
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    temporal = r.get_json()["password_temporal"]
    fila = mundo.usuario("juridica@ejemplo.invalid")
    assert (fila["debe_cambiar_password"], fila["version_credenciales"]) == (1, 1) and temporal not in fila["password_hash"]

    assert persona.get("/api/clientes/listado").status_code == 401, "la sesión anterior quedó invalidada"
    assert _entrar("juridica@ejemplo.invalid", CLAVE_JURIDICA)[1].status_code == 401, "la contraseña anterior dejó de servir"
    nueva, r = _entrar("juridica@ejemplo.invalid", temporal)
    assert r.status_code == 200 and r.get_json()["usuario"]["debe_cambiar_password"] is True
    assert nueva.get("/api/clientes/listado").get_json()["codigo"] == "CAMBIO_PASSWORD_OBLIGATORIO"
    assert nueva.post("/api/auth/cambiar-password", json={"password_actual": temporal, "password_nueva": NUEVA, "confirmacion": NUEVA}).status_code == 200
    assert nueva.get("/api/clientes/listado").status_code == 200

    evento = _auditoria(mundo, "CONTRASENA_TEMPORAL_RESTABLECIDA")
    assert len(evento) == 1 and evento[0]["id_usuario"] == 1 and evento[0]["id_registro"] == destino
    for fila_aud in _auditoria(mundo):
        assert temporal not in (fila_aud["datos_nuevos"] or "") and "$2" not in (fila_aud["datos_nuevos"] or "")


def test_restablecimientos_sucesivos_solo_sirve_la_ultima_temporal(mundo):
    admin = _admin()
    destino = mundo.usuario("juridica@ejemplo.invalid")["id_usuario"]
    t1 = admin.post(f"/api/usuarios/{destino}/restablecer-password", json={"confirmar": True}).get_json()["password_temporal"]
    t2 = admin.post(f"/api/usuarios/{destino}/restablecer-password", json={"confirmar": True}).get_json()["password_temporal"]
    t3 = admin.post(f"/api/usuarios/{destino}/restablecer-password", json={"confirmar": True}).get_json()["password_temporal"]
    assert len({t1, t2, t3}) == 3
    assert _entrar("juridica@ejemplo.invalid", t1)[1].status_code == 401
    assert _entrar("juridica@ejemplo.invalid", t2)[1].status_code == 401
    assert _entrar("juridica@ejemplo.invalid", t3)[1].status_code == 200
    assert mundo.usuario("juridica@ejemplo.invalid")["version_credenciales"] == 3


def test_el_administrador_no_restablece_su_propia_cuenta_ni_cuentas_inexistentes(mundo):
    admin = _admin()
    assert admin.post("/api/usuarios/1/restablecer-password", json={"confirmar": True}).status_code == 409
    assert admin.post("/api/usuarios/9999/restablecer-password", json={"confirmar": True}).status_code == 404
    assert mundo.usuario("admin@ejemplo.invalid")["version_credenciales"] == 0
    assert admin.get("/api/auth/me").status_code == 200, "no se bloqueó el acceso del administrador"
    # Su cambio personal sigue disponible (voluntario: pide la actual)
    nueva = "Admin-Personal-Nueva-2"
    assert admin.post("/api/auth/cambiar-password", json={"password_actual": CLAVE_ADMIN, "password_nueva": nueva, "confirmacion": nueva}).status_code == 200
    assert _entrar("admin@ejemplo.invalid", CLAVE_ADMIN)[1].status_code == 401
    assert _entrar("admin@ejemplo.invalid", nueva)[1].status_code == 200


# ------------------------------------------------------------------ recuperación por correo
def test_la_recuperacion_por_correo_respeta_el_mismo_estado_de_seguridad(mundo):
    admin = _admin()
    temporal = _crear(admin).get_json()["password_temporal"]
    destino = mundo.usuario("nueva@ejemplo.invalid")["id_usuario"]
    persona, _ = _entrar("nueva@ejemplo.invalid", temporal)
    otra_temporal = admin.post(f"/api/usuarios/{destino}/restablecer-password", json={"confirmar": True}).get_json()["password_temporal"]
    # Un enlace emitido ANTES del restablecimiento ya no sirve (el restablecimiento los anula).
    token_viejo = "token-viejo-ficticio-" + "a" * 20
    mundo.sql("INSERT INTO token_recuperacion (id_usuario, token_hash, fecha_expiracion, utilizado) VALUES (%s, %s, %s, 1)",
              (destino, hashlib.sha256(token_viejo.encode()).hexdigest(), datetime.datetime.now() + datetime.timedelta(minutes=30)))
    c = _cliente()
    assert c.post("/api/auth/restablecer", json={"token": token_viejo, "password": NUEVA}).status_code == 400
    # Un enlace nuevo, con contraseña elegida por la persona: quita la obligación e invalida lo anterior.
    token = "token-vigente-ficticio-" + "b" * 20
    mundo.sql("INSERT INTO token_recuperacion (id_usuario, token_hash, fecha_expiracion) VALUES (%s, %s, %s)",
              (destino, hashlib.sha256(token.encode()).hexdigest(), datetime.datetime.now() + datetime.timedelta(minutes=30)))
    r = c.post("/api/auth/restablecer", json={"token": token, "password": NUEVA})
    assert r.status_code == 200
    fila = mundo.usuario("nueva@ejemplo.invalid")
    assert fila["debe_cambiar_password"] == 0 and fila["version_credenciales"] == 2  # restablecimiento + recuperación
    assert _entrar("nueva@ejemplo.invalid", temporal)[1].status_code == 401
    assert _entrar("nueva@ejemplo.invalid", otra_temporal)[1].status_code == 401
    assert persona.get("/api/auth/me").status_code == 401
    ok, r = _entrar("nueva@ejemplo.invalid", NUEVA)
    assert r.status_code == 200 and ok.get("/api/clientes/listado").status_code == 200


def test_restablecer_anula_los_enlaces_de_recuperacion_vigentes(mundo):
    admin = _admin()
    destino = mundo.usuario("juridica@ejemplo.invalid")["id_usuario"]
    token = "token-pendiente-ficticio-" + "c" * 20
    mundo.sql("INSERT INTO token_recuperacion (id_usuario, token_hash, fecha_expiracion) VALUES (%s, %s, %s)",
              (destino, hashlib.sha256(token.encode()).hexdigest(), datetime.datetime.now() + datetime.timedelta(minutes=30)))
    admin.post(f"/api/usuarios/{destino}/restablecer-password", json={"confirmar": True})
    assert _cliente().post("/api/auth/restablecer", json={"token": token, "password": NUEVA}).status_code == 400
