# -*- coding: utf-8 -*-
"""RF46 — Alertando y Notificando.

Criterios (Documento 0, Tabla 7.46): las notificaciones se diferencian por
tipo e importancia, se pueden marcar como leídas, las críticas se destacan,
el menú muestra cuántas no se han leído y se personalizan según el rol.

La base es la tabla NOTIFICACION que ya usaban RF51–RF53 y RF76; RF46 le
agrega `importancia` y extiende `crear_notificacion`, sin otra vía de INSERT.
Corre sobre SQLite en memoria reutilizando el harness de RF76.
"""
import re
import sqlite3
from pathlib import Path

import pytest

import backend.routes.notificaciones_routes as notificaciones_routes
from backend.app import app as flask_app
from backend.routes.notificaciones_routes import (
    IMPORTANCIA_ALTA,
    IMPORTANCIA_CRITICA,
    IMPORTANCIA_NORMAL,
    IMPORTANCIAS,
    crear_notificacion,
)
from tests.test_rf76_revision_aprobacion_rechazo import (  # noqa: F401  (fixtures)
    _Conexion,
    _enviar_a_revision,
    _login,
    base,
    cliente as cliente_rf76,
)

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def cliente(cliente_rf76, base, monkeypatch):
    monkeypatch.setattr(notificaciones_routes, "get_connection", lambda: _Conexion(base))
    return cliente_rf76


def _sembrar(base, filas):
    base.executemany(
        "INSERT INTO notificacion (id_usuario, tipo, importancia, mensaje, fecha, leida) VALUES (?, ?, ?, ?, ?, ?)",
        filas,
    )
    base.commit()


def _avisos(base, **filtros):
    consulta = "SELECT * FROM notificacion"
    if filtros:
        consulta += " WHERE " + " AND ".join(f"{clave} = ?" for clave in filtros)
    return [dict(f) for f in base.execute(consulta + " ORDER BY id_notificacion", tuple(filtros.values())).fetchall()]


# --- C1: tipo e importancia ---

def test_el_listado_devuelve_tipo_e_importancia(cliente, base):
    _sembrar(base, [
        (2, "SEGURIDAD", "CRITICA", "Alerta", "2026-09-10 10:00:00", 0),
        (2, "CAMBIO_ESTADO_TAREA", "NORMAL", "Aviso", "2026-09-09 10:00:00", 0),
    ])
    _login(cliente, "responsable@nahan.local")

    datos = cliente.get("/api/notificaciones").get_json()

    assert [(n["tipo"], n["importancia"]) for n in datos["notificaciones"]] == [
        ("SEGURIDAD", "CRITICA"),
        ("CAMBIO_ESTADO_TAREA", "NORMAL"),
    ]
    assert datos["no_leidas"] == 2


def test_las_importancias_validas():
    assert IMPORTANCIAS == (IMPORTANCIA_NORMAL, IMPORTANCIA_ALTA, IMPORTANCIA_CRITICA)
    assert (IMPORTANCIA_NORMAL, IMPORTANCIA_ALTA, IMPORTANCIA_CRITICA) == ("NORMAL", "ALTA", "CRITICA")


def test_el_helper_usa_normal_por_defecto_y_guarda_la_importancia(base):
    cursor = _Conexion(base).cursor()

    crear_notificacion(cursor, 2, "CAMBIO_ESTADO_TAREA", "sin importancia explicita")
    crear_notificacion(cursor, 2, "SEGURIDAD", "critica", "/x", importancia=IMPORTANCIA_CRITICA)
    crear_notificacion(cursor, 2, "ASIGNACION_TAREA", "alta", importancia=IMPORTANCIA_ALTA)

    assert [a["importancia"] for a in _avisos(base)] == ["NORMAL", "CRITICA", "ALTA"]


def test_el_helper_mantiene_la_compatibilidad_con_las_llamadas_antiguas(base):
    cursor = _Conexion(base).cursor()

    crear_notificacion(cursor, 2, "CAMBIO_ESTADO_TAREA", "mensaje", "/url", 1)   # posicional, como antes
    crear_notificacion(cursor, 2, "CAMBIO_ESTADO_TAREA", "propio", id_usuario_actor=2)  # no se autonotifica

    (aviso,) = _avisos(base)
    assert (aviso["tipo"], aviso["importancia"], aviso["url_destino"]) == ("CAMBIO_ESTADO_TAREA", "NORMAL", "/url")


@pytest.mark.parametrize("valor", ["URGENTE", "critica", "", None, 3])
def test_una_importancia_invalida_se_rechaza_sin_escribir(base, valor):
    cursor = _Conexion(base).cursor()

    with pytest.raises(ValueError):
        crear_notificacion(cursor, 2, "SEGURIDAD", "mensaje", importancia=valor)

    assert _avisos(base) == []


def test_la_migracion_007_conserva_las_notificaciones_existentes_como_normales():
    sql = (RAIZ / "database" / "migraciones" / "007_notificacion_importancia.sql").read_text(encoding="utf-8")
    sentencia = " ".join(l for l in sql.splitlines() if not l.strip().startswith("--")).strip().rstrip(";")
    assert "ADD COLUMN importancia VARCHAR(10) NOT NULL DEFAULT 'NORMAL'" in sentencia
    assert "DROP" not in sentencia.upper() and "DELETE" not in sentencia.upper()

    antigua = sqlite3.connect(":memory:")
    antigua.executescript(
        "CREATE TABLE notificacion (id_notificacion INTEGER PRIMARY KEY, id_usuario INTEGER, tipo TEXT, "
        "mensaje TEXT, leida INTEGER DEFAULT 0);"
        "INSERT INTO notificacion (id_usuario, tipo, mensaje, leida) VALUES (2, 'SEGURIDAD', 'previa', 1);"
    )
    antigua.execute(sentencia.replace(" AFTER tipo", ""))  # AFTER es solo de MySQL

    assert antigua.execute("SELECT tipo, importancia, leida, mensaje FROM notificacion").fetchall() == [
        ("SEGURIDAD", "NORMAL", 1, "previa")
    ]


def test_el_esquema_base_y_el_migrador_conocen_la_importancia():
    esquema = (RAIZ / "database" / "nahan_asesores.sql").read_text(encoding="utf-8")
    tabla = esquema[esquema.index("CREATE TABLE notificacion"):]
    tabla = tabla[:tabla.index(");")]
    assert "importancia VARCHAR(10) NOT NULL DEFAULT 'NORMAL'" in tabla

    migrar = (RAIZ / "database" / "migrar.py").read_text(encoding="utf-8")
    assert '"007": [(_COLUMNA, ("notificacion", "importancia"))]' in migrar


# --- C2 y C4: leídas y contador ---

def test_marcar_una_propia_como_leida_baja_el_contador(cliente, base):
    _sembrar(base, [
        (2, "SEGURIDAD", "CRITICA", "a", "2026-09-10 10:00:00", 0),
        (2, "CAMBIO_ESTADO_TAREA", "NORMAL", "b", "2026-09-09 10:00:00", 0),
    ])
    _login(cliente, "responsable@nahan.local")
    assert cliente.get("/api/notificaciones/contador").get_json() == {"no_leidas": 2}

    respuesta = cliente.put("/api/notificaciones/1/leida")

    assert respuesta.status_code == 200
    assert respuesta.get_json()["no_leidas"] == 1
    assert cliente.get("/api/notificaciones/contador").get_json() == {"no_leidas": 1}
    assert _avisos(base, id_notificacion=1)[0]["importancia"] == "CRITICA"  # la importancia no cambia


def test_una_notificacion_ajena_responde_404_y_no_se_modifica(cliente, base):
    _sembrar(base, [(1, "SEGURIDAD", "CRITICA", "del admin", "2026-09-10 10:00:00", 0)])
    _login(cliente, "responsable@nahan.local")

    assert cliente.put("/api/notificaciones/1/leida").status_code == 404
    assert cliente.put("/api/notificaciones/999/leida").status_code == 404
    assert _avisos(base)[0]["leida"] == 0


def test_leer_todas_solo_afecta_a_las_propias_y_el_contador_es_propio(cliente, base):
    _sembrar(base, [
        (2, "SEGURIDAD", "CRITICA", "mia 1", "2026-09-10 10:00:00", 0),
        (2, "CAMBIO_ESTADO_TAREA", "NORMAL", "mia 2", "2026-09-09 10:00:00", 0),
        (3, "SEGURIDAD", "CRITICA", "ajena", "2026-09-08 10:00:00", 0),
        (1, "SEGURIDAD", "CRITICA", "del admin", "2026-09-07 10:00:00", 0),
    ])
    _login(cliente, "responsable@nahan.local")

    assert cliente.get("/api/notificaciones/contador").get_json() == {"no_leidas": 2}
    respuesta = cliente.put("/api/notificaciones/leer-todas")

    assert respuesta.get_json()["marcadas"] == 2
    assert [(a["id_usuario"], a["leida"]) for a in _avisos(base)] == [(2, 1), (2, 1), (3, 0), (1, 0)]
    assert cliente.get("/api/notificaciones/contador").get_json() == {"no_leidas": 0}


def test_cada_usuario_solo_lista_las_suyas_tambien_el_administrador(cliente, base):
    _sembrar(base, [
        (2, "SEGURIDAD", "CRITICA", "del responsable", "2026-09-10 10:00:00", 0),
        (3, "SEGURIDAD", "CRITICA", "del ajeno", "2026-09-10 11:00:00", 0),
    ])
    _login(cliente, "admin@nahan.local")

    assert cliente.get("/api/notificaciones").get_json()["notificaciones"] == []
    assert cliente.get("/api/notificaciones/contador").get_json() == {"no_leidas": 0}


def test_el_listado_conserva_el_orden_y_el_limite(cliente, base):
    _sembrar(base, [
        (2, "CAMBIO_ESTADO_TAREA", "NORMAL", "vieja", "2026-09-01 10:00:00", 1),
        (2, "SEGURIDAD", "CRITICA", "nueva", "2026-09-10 10:00:00", 0),
        (2, "ASIGNACION_TAREA", "ALTA", "media", "2026-09-05 10:00:00", 0),
    ])
    _login(cliente, "responsable@nahan.local")

    mensajes = [n["mensaje"] for n in cliente.get("/api/notificaciones").get_json()["notificaciones"]]
    assert mensajes == ["nueva", "media", "vieja"]

    assert [n["mensaje"] for n in cliente.get("/api/notificaciones?solo_no_leidas=1&limite=1").get_json()["notificaciones"]] == ["nueva"]


def test_las_rutas_de_notificaciones_exigen_sesion(cliente):
    assert cliente.get("/api/notificaciones").status_code == 401
    assert cliente.get("/api/notificaciones/contador").status_code == 401
    assert cliente.put("/api/notificaciones/1/leida").status_code == 401
    assert cliente.put("/api/notificaciones/leer-todas").status_code == 401


# --- C3 y C5: críticas y personalización por rol (flujo de RF76) ---

def test_el_envio_a_revision_avisa_solo_a_los_administradores_como_critico(cliente, base):
    _enviar_a_revision(cliente)

    (aviso,) = _avisos(base)
    assert (aviso["id_usuario"], aviso["tipo"], aviso["importancia"]) == (1, "REVISION_TAREA", "CRITICA")
    assert _avisos(base, id_usuario=2) == []   # quien envía no recibe la alerta administrativa
    assert _avisos(base, id_usuario=3) == []   # un usuario de otra área tampoco

    _login(cliente, "ajeno@nahan.local")
    assert cliente.get("/api/notificaciones").get_json()["notificaciones"] == []

    _login(cliente, "admin@nahan.local")
    (vista,) = cliente.get("/api/notificaciones").get_json()["notificaciones"]
    assert (vista["tipo"], vista["importancia"]) == ("REVISION_TAREA", "CRITICA")


def test_el_resultado_de_la_revision_llega_al_responsable_sin_ser_critico(cliente, base):
    _enviar_a_revision(cliente)
    _login(cliente, "admin@nahan.local")
    assert cliente.put("/api/tareas/1/revision", json={"accion": "aprobar"}).status_code == 200

    (aviso,) = _avisos(base, id_usuario=2)
    assert (aviso["tipo"], aviso["importancia"]) == ("REVISION_TAREA", "NORMAL")


def test_las_asignaciones_son_de_importancia_alta_y_el_cambio_de_estado_normal(cliente, base):
    _login(cliente, "admin@nahan.local")
    assert cliente.put("/api/tareas/1/asignar", json={"id_responsable": 3}).status_code == 200
    assert cliente.put("/api/tareas/1/estado", json={"estado": "PENDIENTE"}).status_code == 200

    assert [(a["id_usuario"], a["importancia"]) for a in _avisos(base, tipo="REASIGNACION_TAREA")] == [(3, "ALTA")]
    assert [(a["id_usuario"], a["importancia"]) for a in _avisos(base, tipo="CAMBIO_ESTADO_TAREA")] == [(3, "NORMAL")]


def test_la_solicitud_de_restablecimiento_es_critica_solo_para_administradores(base, monkeypatch):
    import backend.routes.auth_routes as auth_routes

    cursor = _Conexion(base).cursor(dictionary=True)
    auth_routes._avisar_a_administradores(cursor, {"email": "ajeno@nahan.local", "nombres": "Usuario Ajeno"})

    avisos = _avisos(base)
    assert [(a["id_usuario"], a["tipo"], a["importancia"]) for a in avisos] == [(1, "SEGURIDAD", "CRITICA")]
    assert "ajeno@nahan.local" in avisos[0]["mensaje"]


# --- Una sola vía de escritura ---

def test_solo_el_helper_central_inserta_en_notificacion():
    archivos = [
        str(ruta.relative_to(RAIZ))
        for ruta in (RAIZ / "backend").rglob("*.py")
        if re.search(r"INSERT\s+INTO\s+notificacion", ruta.read_text(encoding="utf-8"), re.I)
    ]

    assert archivos == ["backend/routes/notificaciones_routes.py"]


def test_los_productores_existentes_usan_el_helper_central():
    for modulo in ("routes/tareas_routes.py", "routes/auth_routes.py", "tareas_programadas.py"):
        texto = (RAIZ / "backend" / modulo).read_text(encoding="utf-8")
        assert "crear_notificacion(" in texto, modulo


# --- Frontend ---

def test_la_bandeja_etiqueta_la_revision_y_destaca_las_criticas_sin_html_inseguro():
    js = (RAIZ / "frontend" / "assets" / "js" / "notificaciones.js").read_text(encoding="utf-8")
    css = (RAIZ / "frontend" / "assets" / "css" / "notificaciones.css").read_text(encoding="utf-8")

    assert 'REVISION_TAREA: "Revisión de tarea"' in js
    assert 'CRITICA: "⚠ Crítica"' in js          # indicador textual, no solo color
    assert 'classList.add("critica")' in js
    assert "hasOwnProperty.call(ETIQUETAS_IMPORTANCIA" in js
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js
    assert ".notificacion-item.critica" in css
    assert ".importancia-critica" in css
