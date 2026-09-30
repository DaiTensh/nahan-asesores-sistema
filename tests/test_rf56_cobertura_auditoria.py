# -*- coding: utf-8 -*-
"""RF56 — cobertura de auditoría por módulo.

Documento 0, Tabla 7.56: «El historial registra acciones de todos los módulos
del sistema». Estas pruebas ejecutan las operaciones de clientes, tareas,
documentos y control de horas, y comprueban que cada una deja su evento en
AUDITORIA mediante registrar_auditoria(), dentro de la misma transacción, y
que el evento llega al historial global (RF56), al consolidado (RF40) y al
historial del cliente (RF13).

Corre sobre SQLite en memoria. El cursor imita al de mysql-connector: una
sentencia ejecutada con un resultado anterior sin leer falla.
"""
import io
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

import backend.routes.auth_routes as auth_routes
import backend.routes.clientes_routes as clientes_routes
import backend.routes.control_horas_routes as control_horas_routes
import backend.routes.documentos_routes as documentos_routes
import backend.routes.historial_routes as historial_routes
import backend.routes.reportes_routes as reportes_routes
import backend.routes.tareas_routes as tareas_routes
import backend.utils.auth as auth_utils
from backend.app import app as flask_app
from backend.utils.auditoria import acciones_de_registros, modulo_de_tabla
from tests.conftest import normalize_sql

RAIZ = Path(__file__).resolve().parents[1]

ESQUEMA = """
CREATE TABLE rol (id_rol INTEGER PRIMARY KEY AUTOINCREMENT, nombre_rol TEXT);
CREATE TABLE area (id_area INTEGER PRIMARY KEY AUTOINCREMENT, nombre_area TEXT);
CREATE TABLE usuario (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT, id_rol INTEGER, id_area INTEGER,
    nombres TEXT, email TEXT UNIQUE, password_hash TEXT, estado TEXT DEFAULT 'ACTIVO');
CREATE TABLE cliente (
    id_cliente INTEGER PRIMARY KEY AUTOINCREMENT, rut TEXT UNIQUE, razon_social TEXT,
    email TEXT, telefono TEXT, direccion TEXT, estado TEXT DEFAULT 'ACTIVO',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE cliente_area (id_cliente INTEGER, id_area INTEGER, fecha_asignacion DATE);
CREATE TABLE tarea (
    id_tarea INTEGER PRIMARY KEY AUTOINCREMENT, id_cliente INTEGER, id_area INTEGER,
    id_responsable INTEGER, id_creador INTEGER, titulo TEXT, descripcion TEXT,
    estado TEXT DEFAULT 'PENDIENTE', prioridad TEXT DEFAULT 'MEDIA',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP, fecha_vencimiento DATE);
CREATE TABLE observacion_cliente (
    id_observacion INTEGER PRIMARY KEY AUTOINCREMENT, id_cliente INTEGER,
    id_usuario INTEGER, texto TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE documento (
    id_documento INTEGER PRIMARY KEY AUTOINCREMENT, id_cliente INTEGER,
    nombre_documento TEXT, tipo_documento TEXT, url_archivo TEXT, descripcion TEXT,
    fecha_subida DATETIME DEFAULT CURRENT_TIMESTAMP, subido_por INTEGER,
    estado TEXT DEFAULT 'ACTIVO');
CREATE TABLE tarea_documento (
    id_tarea_documento INTEGER PRIMARY KEY AUTOINCREMENT, id_tarea INTEGER, id_documento INTEGER);
CREATE TABLE notificacion (
    id_notificacion INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER, tipo TEXT, importancia TEXT NOT NULL DEFAULT 'NORMAL',
    mensaje TEXT, url_destino TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP, leida INTEGER DEFAULT 0);
CREATE TABLE auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER,
    tabla_afectada TEXT, id_registro INTEGER, accion TEXT, datos_anteriores TEXT,
    datos_nuevos TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE parametros_sistema (
    id_parametro INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_parametro TEXT UNIQUE, valor_parametro TEXT, tipo_dato TEXT, descripcion TEXT);

INSERT INTO rol (nombre_rol) VALUES ('ADMINISTRADOR'), ('USUARIO_AREA_JURIDICA');
INSERT INTO area (nombre_area) VALUES ('JURIDICA'), ('CONTABLE');
INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) VALUES
 (1, 1, 'Admin Nahan', 'admin@nahan.local', 'hash'),
 (2, 1, 'Usuaria Juridica', 'juridica@nahan.local', 'hash');
INSERT INTO cliente (rut, razon_social, email, telefono, direccion) VALUES
 ('11.111.111-1', 'Cliente Base', 'base@cliente.cl', '111', 'Calle 1'),
 ('22.222.222-2', 'Otro Cliente', 'otro@cliente.cl', '222', 'Calle 2');
INSERT INTO cliente_area (id_cliente, id_area, fecha_asignacion) VALUES (1, 1, '2026-09-01');
INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo) VALUES
 (1, 1, 2, 1, 'Tarea existente');
INSERT INTO parametros_sistema (nombre_parametro, valor_parametro, tipo_dato, descripcion) VALUES
 ('ADJUNTOS_TAMANO_MAXIMO_MB', '1', 'INT', 'limite de prueba'),
 ('ADJUNTOS_EXTENSIONES_PERMITIDAS', 'pdf,png', 'VARCHAR', 'extensiones de prueba');
"""


class _Cursor:
    def __init__(self, conexion, dictionary):
        self._cursor = conexion.cursor()
        self._dictionary = dictionary
        self._filas = []
        self._sin_leer = False
        self.lastrowid = None
        self.rowcount = 0

    def _empaquetar(self, fila):
        return dict(fila) if self._dictionary else tuple(fila)

    def execute(self, sql, params=()):
        if self._sin_leer:
            raise RuntimeError("Unread result found")
        self._cursor.execute(sql.replace("%s", "?"), tuple(params))
        self.lastrowid = self._cursor.lastrowid
        self.rowcount = self._cursor.rowcount
        if self._cursor.description is not None:
            self._filas = self._cursor.fetchall()
            self._sin_leer = True
        else:
            self._filas = []

    def fetchone(self):
        if not self._filas:
            self._sin_leer = False
            return None
        fila = self._filas.pop(0)
        if not self._filas:
            self._sin_leer = False
        return self._empaquetar(fila)

    def fetchall(self):
        filas, self._filas = self._filas, []
        self._sin_leer = False
        return [self._empaquetar(fila) for fila in filas]

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
    conexion.execute("UPDATE usuario SET password_hash = ?", (hash_password("x"),))
    conexion.commit()
    yield conexion
    conexion.close()


@pytest.fixture
def cliente(base, monkeypatch, tmp_path):
    conexion_falsa = lambda: _Conexion(base)
    for modulo in (auth_routes, auth_utils, clientes_routes, tareas_routes,
                   documentos_routes, historial_routes, reportes_routes):
        monkeypatch.setattr(modulo, "get_connection", conexion_falsa)
    monkeypatch.setenv("ADJUNTOS_DIR", str(tmp_path))
    # RF30 audita el inicio de sesión. Esta prueba no trata de sesiones y cuenta
    # sus propios eventos, así que el login que usa como preparación no debe
    # sumar uno; el LOGIN real se comprueba en test_rf30_historial_accesos.py.
    monkeypatch.setattr(auth_routes, "registrar_auditoria", lambda *args, **kwargs: None)

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as cliente_http:
        yield cliente_http


def _login(cliente, email="admin@nahan.local"):
    assert cliente.post("/api/login", json={"email": email, "password": "x"}).status_code == 200


def _eventos(base, accion):
    return [dict(fila) for fila in base.execute(
        "SELECT * FROM auditoria WHERE accion = ? ORDER BY id_auditoria", (accion,)
    ).fetchall()]


def _total_auditoria(base):
    return base.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0]


# --- Clientes ---

def test_registrar_cliente_deja_un_evento_con_el_cliente_creado(cliente, base):
    _login(cliente, "juridica@nahan.local")

    respuesta = cliente.post("/api/clientes", json={
        "rut": "33.333.333-3", "razon_social": "Cliente Nuevo", "email": "nuevo@cliente.cl",
        "telefono": "333", "direccion": "Calle 3", "areas": [1, 2],
    })

    assert respuesta.status_code == 201
    id_cliente = base.execute("SELECT id_cliente FROM cliente WHERE rut = '33.333.333-3'").fetchone()[0]
    eventos = _eventos(base, "CLIENTE_CREADO")
    assert len(eventos) == 1
    assert eventos[0]["tabla_afectada"] == "cliente"
    assert eventos[0]["id_registro"] == id_cliente
    assert eventos[0]["id_usuario"] == 2
    assert "razon_social=Cliente Nuevo" in eventos[0]["datos_nuevos"]
    assert "areas=1,2" in eventos[0]["datos_nuevos"]


def test_registrar_cliente_rechazado_no_deja_evento(cliente, base):
    _login(cliente)

    duplicado = cliente.post("/api/clientes", json={
        "rut": "11.111.111-1", "razon_social": "Repetido", "areas": [1],
    })
    sin_area = cliente.post("/api/clientes", json={"rut": "44.444.444-4", "razon_social": "Sin área"})

    assert duplicado.status_code == 400
    assert sin_area.status_code == 400
    assert _total_auditoria(base) == 0


def test_modificar_cliente_deja_el_antes_y_el_despues(cliente, base):
    _login(cliente)

    respuesta = cliente.put("/api/clientes/1", json={
        "razon_social": "Cliente Base Renombrado", "email": "base@cliente.cl",
        "telefono": "999", "direccion": "Calle 1", "areas": [1, 2],
    })

    assert respuesta.status_code == 200
    eventos = _eventos(base, "CLIENTE_MODIFICADO")
    assert len(eventos) == 1
    assert eventos[0]["tabla_afectada"] == "cliente"
    assert eventos[0]["id_registro"] == 1
    assert eventos[0]["id_usuario"] == 1
    assert "razon_social=Cliente Base," in eventos[0]["datos_anteriores"]
    assert "telefono=111" in eventos[0]["datos_anteriores"]
    assert "areas=1" in eventos[0]["datos_anteriores"]
    assert "razon_social=Cliente Base Renombrado" in eventos[0]["datos_nuevos"]
    assert "telefono=999" in eventos[0]["datos_nuevos"]
    assert "areas=1,2" in eventos[0]["datos_nuevos"]


def test_modificar_cliente_inexistente_no_deja_evento(cliente, base):
    _login(cliente)

    respuesta = cliente.put("/api/clientes/999", json={"razon_social": "X", "areas": [1]})

    assert respuesta.status_code == 404
    assert _total_auditoria(base) == 0


def test_registrar_observacion_deja_evento_sin_copiar_el_texto(cliente, base):
    _login(cliente, "juridica@nahan.local")

    respuesta = cliente.post("/api/clientes/1/observaciones", json={"texto": "Dato reservado del cliente"})

    assert respuesta.status_code == 201
    id_observacion = base.execute("SELECT id_observacion FROM observacion_cliente").fetchone()[0]
    eventos = _eventos(base, "OBSERVACION_CREADA")
    assert len(eventos) == 1
    assert eventos[0]["tabla_afectada"] == "observacion_cliente"
    assert eventos[0]["id_registro"] == id_observacion
    assert eventos[0]["id_usuario"] == 2
    assert eventos[0]["datos_nuevos"] == "id_cliente=1"
    assert "reservado" not in (eventos[0]["datos_nuevos"] or "")


# --- Tareas ---

def _crear_tarea(cliente, **cambios):
    datos = {"id_cliente": 1, "id_area": 1, "id_responsable": 2, "titulo": "Tarea nueva", "prioridad": "ALTA"}
    datos.update(cambios)
    return cliente.post("/api/tareas", json=datos)


def test_crear_tarea_deja_el_evento_tarea_creada(cliente, base):
    _login(cliente)

    assert _crear_tarea(cliente).status_code == 201

    id_tarea = base.execute("SELECT id_tarea FROM tarea WHERE titulo = 'Tarea nueva'").fetchone()[0]
    eventos = _eventos(base, "TAREA_CREADA")
    assert len(eventos) == 1
    assert eventos[0]["tabla_afectada"] == "tarea"
    assert eventos[0]["id_registro"] == id_tarea
    assert eventos[0]["id_usuario"] == 1
    assert f"id_tarea={id_tarea}, id_cliente=1" in eventos[0]["datos_nuevos"]
    assert "titulo=Tarea nueva" in eventos[0]["datos_nuevos"]
    # La notificación de RF52 sigue apuntando a la tarea creada.
    aviso = base.execute("SELECT url_destino FROM notificacion WHERE id_usuario = 2").fetchone()
    assert aviso["url_destino"].endswith(f"id={id_tarea}")


def test_crear_tarea_en_ambas_areas_deja_un_evento_por_tarea(cliente, base):
    _login(cliente)

    assert _crear_tarea(cliente, id_area="AMBAS", titulo="Tarea doble").status_code == 201

    ids = [fila[0] for fila in base.execute("SELECT id_tarea FROM tarea WHERE titulo = 'Tarea doble' ORDER BY id_tarea")]
    eventos = _eventos(base, "TAREA_CREADA")
    assert len(ids) == 2
    assert [evento["id_registro"] for evento in eventos] == ids


def test_crear_tarea_rechazada_no_deja_evento(cliente, base):
    _login(cliente)

    assert _crear_tarea(cliente, id_cliente=999).status_code == 404
    assert _crear_tarea(cliente, id_responsable=999).status_code == 422
    assert _total_auditoria(base) == 0


# --- Documentos ---

def test_registrar_referencia_de_documento_deja_evento(cliente, base):
    _login(cliente, "juridica@nahan.local")

    respuesta = cliente.post("/api/clientes/1/documentos", json={
        "nombre_documento": "Escritura", "tipo_documento": "Contrato",
        "ubicacion_referencia": "Carpeta compartida/escritura.pdf",
    })

    assert respuesta.status_code == 201
    eventos = _eventos(base, "DOCUMENTO_REFERENCIADO")
    assert len(eventos) == 1
    assert eventos[0]["tabla_afectada"] == "documento"
    assert eventos[0]["id_registro"] == respuesta.get_json()["id_documento"]
    assert eventos[0]["id_usuario"] == 2
    assert "id_cliente=1" in eventos[0]["datos_nuevos"]
    assert "nombre_documento=Escritura" in eventos[0]["datos_nuevos"]


def test_referencia_duplicada_no_deja_un_segundo_evento(cliente, base):
    _login(cliente)
    datos = {"nombre_documento": "Escritura", "tipo_documento": "Contrato", "ubicacion_referencia": "ruta"}
    assert cliente.post("/api/clientes/1/documentos", json=datos).status_code == 201

    assert cliente.post("/api/clientes/1/documentos", json=datos).status_code == 400
    assert len(_eventos(base, "DOCUMENTO_REFERENCIADO")) == 1


def test_adjuntar_archivo_a_una_tarea_deja_evento(cliente, base):
    _login(cliente, "juridica@nahan.local")

    respuesta = cliente.post(
        "/api/tareas/1/documentos",
        data={"archivo": (io.BytesIO(b"contenido"), "respaldo.pdf")},
        content_type="multipart/form-data",
    )

    assert respuesta.status_code == 201
    eventos = _eventos(base, "DOCUMENTO_ADJUNTADO")
    assert len(eventos) == 1
    assert eventos[0]["tabla_afectada"] == "documento"
    assert eventos[0]["id_registro"] == respuesta.get_json()["id_documento"]
    assert eventos[0]["id_usuario"] == 2
    assert "id_tarea=1" in eventos[0]["datos_nuevos"]
    assert "nombre_documento=respaldo.pdf" in eventos[0]["datos_nuevos"]


def test_adjunto_rechazado_no_deja_evento(cliente, base):
    _login(cliente)

    respuesta = cliente.post(
        "/api/tareas/1/documentos",
        data={"archivo": (io.BytesIO(b"contenido"), "script.exe")},
        content_type="multipart/form-data",
    )

    assert respuesta.status_code == 400
    assert _total_auditoria(base) == 0


# --- Control de horas (SQL propio de MySQL: se usa la conexión simulada) ---

def _handler_control_horas(sql, params, cursor):
    consulta = normalize_sql(sql)
    if "SELECT u.id_usuario, u.estado, r.nombre_rol" in consulta:
        return [{"id_usuario": 2, "estado": "ACTIVO", "nombre_rol": "USUARIO_AREA_JURIDICA"}]
    if "FROM tarea t INNER JOIN cliente c" in consulta:
        return [{"id_tarea": 50, "id_cliente": 10, "id_area": 1, "titulo": "Tarea",
                 "cliente": "Cliente", "cliente_rut": "11.111.111-1"}]
    if "SELECT valor_hora FROM tarifa_hora" in consulta:
        return [{"valor_hora": Decimal("30000.00")}]
    if "INSERT INTO registro_tiempo" in consulta:
        cursor.lastrowid = 77
        return []
    if "SELECT id_registro FROM registro_tiempo" in consulta:
        return [{"id_registro": 77}]
    if "SELECT id_registro, duracion_minutos, tarifa_hora, monto" in consulta:
        return [{"id_registro": 77, "duracion_minutos": Decimal("90.00"),
                 "tarifa_hora": Decimal("30000.00"), "monto": Decimal("45000.00")}]
    if "WHERE rt.id_registro = %s" in consulta:
        return [{"id_registro": 77, "id_tarea": 50, "id_cliente": 10, "tarea": "Tarea",
                 "cliente": "Cliente", "cliente_rut": "11.111.111-1",
                 "inicio": "2026-09-30T09:00:00", "tarifa_hora": Decimal("30000.00")}]
    return []


def _auditorias(conexion):
    return [
        (normalize_sql(sql), params) for sql, params in conexion.executed
        if "INSERT INTO auditoria" in normalize_sql(sql)
    ]


def test_iniciar_temporizador_deja_evento_antes_del_commit(
    client, fake_connection_factory, monkeypatch, iniciar_sesion
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)
    conexion = fake_connection_factory(_handler_control_horas)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: conexion)

    respuesta = client.post("/api/control-horas/iniciar", json={"id_tarea": 50})

    assert respuesta.status_code == 201
    auditorias = _auditorias(conexion)
    assert len(auditorias) == 1
    id_usuario, tabla, id_registro, accion, anteriores, nuevos = auditorias[0][1]
    assert (id_usuario, tabla, id_registro, accion) == (2, "registro_tiempo", 77, "TEMPORIZADOR_INICIADO")
    assert "id_tarea=50" in nuevos and "id_cliente=10" in nuevos
    assert conexion.commits == 1 and conexion.rollbacks == 0


def test_detener_temporizador_deja_evento_con_la_duracion(
    client, fake_connection_factory, monkeypatch, iniciar_sesion
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)
    conexion = fake_connection_factory(_handler_control_horas)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: conexion)

    respuesta = client.post("/api/control-horas/detener", json={})

    assert respuesta.status_code == 200
    auditorias = _auditorias(conexion)
    assert len(auditorias) == 1
    id_usuario, tabla, id_registro, accion, anteriores, nuevos = auditorias[0][1]
    assert (id_usuario, tabla, id_registro, accion) == (2, "registro_tiempo", 77, "TEMPORIZADOR_DETENIDO")
    assert "duracion_minutos=90" in nuevos
    assert conexion.commits == 1 and conexion.rollbacks == 0


def test_temporizador_rechazado_no_deja_evento(
    client, fake_connection_factory, monkeypatch, iniciar_sesion
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def sin_temporizador(sql, params, cursor):
        if "SELECT id_registro FROM registro_tiempo" in normalize_sql(sql):
            return []
        return _handler_control_horas(sql, params, cursor)

    conexion = fake_connection_factory(sin_temporizador)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: conexion)

    respuesta = client.post("/api/control-horas/detener", json={})

    assert respuesta.status_code == 404
    assert _auditorias(conexion) == []
    assert conexion.commits == 0


def test_control_de_horas_tiene_modulo_propio_en_el_historial():
    assert modulo_de_tabla("registro_tiempo") == "Control de horas"


# --- Integración con RF56, RF40 y RF13 ---

def _generar_actividad(cliente):
    _login(cliente)
    assert cliente.post("/api/clientes/1/observaciones", json={"texto": "Nota"}).status_code == 201
    assert _crear_tarea(cliente).status_code == 201
    assert cliente.post("/api/clientes/1/documentos", json={
        "nombre_documento": "Escritura", "tipo_documento": "Contrato", "ubicacion_referencia": "ruta",
    }).status_code == 201
    assert cliente.put("/api/clientes/1", json={
        "razon_social": "Cliente Base", "email": "", "telefono": "", "direccion": "", "areas": [1],
    }).status_code == 200


def test_el_historial_global_muestra_los_nuevos_eventos_con_su_modulo(cliente):
    _generar_actividad(cliente)

    eventos = cliente.get("/api/historial").get_json()["eventos"]

    assert {(evento["accion"], evento["modulo"]) for evento in eventos} == {
        ("OBSERVACION_CREADA", "Clientes"),
        ("TAREA_CREADA", "Tareas"),
        ("DOCUMENTO_REFERENCIADO", "Documentos"),
        ("CLIENTE_MODIFICADO", "Clientes"),
    }
    assert all(evento["usuario"] == "Admin Nahan" for evento in eventos)

    clientes = cliente.get("/api/historial?modulo=Clientes").get_json()["eventos"]
    assert {evento["accion"] for evento in clientes} == {"OBSERVACION_CREADA", "CLIENTE_MODIFICADO"}


def test_el_historial_consolidado_recibe_los_nuevos_eventos(cliente, monkeypatch):
    monkeypatch.setattr(
        reportes_routes, "_registrar_generacion",
        lambda *args, **kwargs: {"id_reporte": 1, "fecha_generacion": "2026-09-30 10:00"},
    )
    _generar_actividad(cliente)

    respuesta = cliente.get("/api/reportes/historial-consolidado?fecha_inicio=2000-01-01&fecha_fin=2999-12-31")
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["total"] == 4
    assert {evento["accion"] for evento in datos["eventos"]} == {
        "OBSERVACION_CREADA", "TAREA_CREADA", "DOCUMENTO_REFERENCIADO", "CLIENTE_MODIFICADO",
    }


def test_el_historial_del_cliente_muestra_la_tarea_creada(cliente, base):
    _generar_actividad(cliente)
    id_tarea = base.execute("SELECT id_tarea FROM tarea WHERE titulo = 'Tarea nueva'").fetchone()[0]

    datos = cliente.get("/api/clientes/1/historial-completo").get_json()

    acciones = [evento["accion"] for evento in datos["historial"]]
    assert sorted(acciones) == [
        "CLIENTE_MODIFICADO", "DOCUMENTO_REFERENCIADO", "OBSERVACION_CREADA", "TAREA_CREADA",
    ]
    assert datos["acciones_disponibles"] == sorted(acciones)
    creada = next(evento for evento in datos["historial"] if evento["accion"] == "TAREA_CREADA")
    assert creada["tabla_afectada"] == "tarea"
    assert creada["id_registro"] == id_tarea
    assert creada["usuario"] == "Admin Nahan"

    filtrado = cliente.get("/api/clientes/1/historial-completo?accion=TAREA_CREADA").get_json()
    assert [evento["accion"] for evento in filtrado["historial"]] == ["TAREA_CREADA"]


def test_la_tarea_creada_no_aparece_en_el_historial_de_otro_cliente(cliente):
    _generar_actividad(cliente)

    datos = cliente.get("/api/clientes/2/historial-completo").get_json()

    assert datos["historial"] == []
    assert datos["acciones_disponibles"] == []


def test_acciones_de_registros_sin_registros_no_consulta(base):
    cursor = _Conexion(base).cursor(dictionary=True)

    assert acciones_de_registros(cursor, []) == []


# --- Reglas transversales ---

RUTAS = ("clientes_routes", "tareas_routes", "documentos_routes", "control_horas_routes")


@pytest.mark.parametrize("modulo", RUTAS)
def test_ninguna_ruta_inserta_en_auditoria_a_mano(modulo):
    codigo = (RAIZ / "backend/routes" / f"{modulo}.py").read_text(encoding="utf-8")

    assert "INSERT INTO auditoria" not in codigo
    assert "registrar_auditoria(" in codigo


def test_la_auditoria_no_guarda_credenciales(cliente, base):
    _generar_actividad(cliente)

    for fila in base.execute("SELECT datos_anteriores, datos_nuevos FROM auditoria"):
        texto = f"{fila[0] or ''} {fila[1] or ''}".lower()
        assert "password" not in texto
        assert "token" not in texto
        assert "hash" not in texto


def test_el_cambio_entre_estados_operativos_deja_evento(cliente, base):
    _login(cliente, "juridica@nahan.local")

    assert cliente.put("/api/tareas/1/estado", json={"estado": "EN_PROCESO"}).status_code == 200

    eventos = _eventos(base, "CAMBIO_ESTADO_TAREA")
    assert len(eventos) == 1
    assert (eventos[0]["tabla_afectada"], eventos[0]["id_registro"], eventos[0]["id_usuario"]) == ("tarea", 1, 2)
    assert eventos[0]["datos_anteriores"] == "id_tarea=1, estado=PENDIENTE"
    assert eventos[0]["datos_nuevos"] == "id_tarea=1, estado=EN_PROCESO"


def test_repetir_el_mismo_estado_no_deja_evento(cliente, base):
    _login(cliente, "juridica@nahan.local")

    assert cliente.put("/api/tareas/1/estado", json={"estado": "PENDIENTE"}).status_code == 200
    assert _total_auditoria(base) == 0


def test_el_historial_del_cliente_muestra_los_cambios_de_estado_de_sus_tareas(cliente):
    _login(cliente)
    cliente.put("/api/tareas/1/estado", json={"estado": "EN_PROCESO"})
    cliente.put("/api/tareas/1/estado", json={"estado": "CANCELADA"})

    historial = cliente.get("/api/clientes/1/historial-completo").get_json()["historial"]

    assert sorted(evento["accion"] for evento in historial) == ["CAMBIO_ESTADO_TAREA", "CANCELAR_TAREA"]
