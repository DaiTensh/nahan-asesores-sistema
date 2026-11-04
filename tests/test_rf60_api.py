"""RF60 — API de administración de respaldos, interfaz y archivos de despliegue.

Pruebas sin MySQL: el servicio se reemplaza por dobles para comprobar la
autenticación, la autorización por rol, la validación de parámetros, la
auditoría y la correspondencia de errores. El recorrido real está en
test_rf60_mysql_real.py.
"""
import datetime
import os
import re
from decimal import Decimal

import pytest

import backend.app as app_module
import backend.routes.respaldos_routes as rutas
from backend.app import app as flask_app
from backend.utils import respaldos as servicio
from backend.utils.auditoria import modulo_de_tabla, modulos_disponibles
from backend.utils.security import hash_password

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENDPOINTS = [
    ("get", "/api/respaldos"),
    ("get", "/api/respaldos/estado"),
    ("post", "/api/respaldos"),
    ("post", "/api/respaldos/1/verificar"),
    ("post", "/api/respaldos/1/restaurar"),
]

CUERPO_RESTAURAR = {"confirmacion": "RESTAURAR", "password": "clave-correcta"}


class ServicioProhibido:
    """Registra cualquier llamada al servicio: los rechazos de acceso no deben llegar a él."""

    def __init__(self, monkeypatch):
        self.llamadas = []
        for nombre in ("ejecutar_respaldo", "ejecutar_restauracion", "verificar_respaldo", "estado_del_sistema"):
            monkeypatch.setattr(servicio, nombre, self._registrar(nombre))
        monkeypatch.setattr(servicio.RegistroMySQL, "listar", self._registrar("listar"))

    def _registrar(self, nombre):
        def llamar(*args, **kwargs):
            self.llamadas.append(nombre)
            raise AssertionError(f"{nombre} no debía ejecutarse")
        return llamar


@pytest.fixture
def auditoria(monkeypatch, fake_connection_factory):
    """Captura lo que la API escribe en AUDITORIA."""
    registradas = []

    def handler(sql, params, cursor):
        if "INSERT INTO auditoria" in sql:
            registradas.append(params)
        return []

    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(rutas, "get_connection", lambda: conexion)
    return registradas


@pytest.fixture(autouse=True)
def sin_rechazos_previos(monkeypatch):
    """Por defecto el usuario no tiene confirmaciones rechazadas recientes; las pruebas del límite lo cambian."""
    monkeypatch.setattr(rutas, "_confirmaciones_rechazadas_recientes", lambda id_usuario: 0)


def admin(iniciar_sesion, usuario_id=1):
    iniciar_sesion(usuario_id=usuario_id, rol_id=1, area_id=3, nombre="Admin Ficticia")


# ---------------------------------------------------------------------------
# Autenticación y autorización
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("metodo,ruta", ENDPOINTS)
def test_sin_sesion_todas_las_rutas_responden_401(client, monkeypatch, metodo, ruta):
    prohibido = ServicioProhibido(monkeypatch)
    cuerpo = {"json": CUERPO_RESTAURAR} if metodo == "post" else {}
    respuesta = getattr(client, metodo)(ruta, **cuerpo)
    assert respuesta.status_code == 401
    assert respuesta.get_json()["error"] == "No autenticado"
    assert prohibido.llamadas == []


@pytest.mark.parametrize("rol_id", [2, 3])
@pytest.mark.parametrize("metodo,ruta", ENDPOINTS)
def test_un_usuario_que_no_es_administrador_recibe_403(client, iniciar_sesion, monkeypatch, rol_id, metodo, ruta):
    prohibido = ServicioProhibido(monkeypatch)
    iniciar_sesion(usuario_id=5, rol_id=rol_id, area_id=1)
    cuerpo = {"json": CUERPO_RESTAURAR} if metodo == "post" else {}
    respuesta = getattr(client, metodo)(ruta, **cuerpo)
    assert respuesta.status_code == 403
    assert "permisos" in respuesta.get_json()["error"]
    assert prohibido.llamadas == []


def test_un_usuario_desactivado_pierde_el_acceso_aunque_conserve_la_sesion(client, iniciar_sesion, monkeypatch):
    prohibido = ServicioProhibido(monkeypatch)
    iniciar_sesion(usuario_id=1, rol_id=1, estado="INACTIVO")
    assert client.post("/api/respaldos").status_code == 401
    assert prohibido.llamadas == []


@pytest.mark.parametrize("metodo,ruta", [
    ("put", "/api/respaldos"), ("delete", "/api/respaldos"), ("patch", "/api/respaldos"),
    ("post", "/api/respaldos/estado"), ("delete", "/api/respaldos/1/restaurar"),
    ("get", "/api/respaldos/1/restaurar"), ("get", "/api/respaldos/1/verificar"),
    ("put", "/api/respaldos/1/restaurar"),
])
def test_los_metodos_no_previstos_responden_405(client, iniciar_sesion, monkeypatch, metodo, ruta):
    ServicioProhibido(monkeypatch)
    admin(iniciar_sesion)
    respuesta = getattr(client, metodo)(ruta)
    assert respuesta.status_code == 405
    assert "error" in respuesta.get_json()


def test_los_paquetes_no_se_pueden_descargar_por_http(client, iniciar_sesion):
    admin(iniciar_sesion)
    for ruta in ("/api/respaldos/1/descargar", "/api/respaldos/1", "/api/respaldos/1/archivo",
                 "/api/respaldos/nahan-respaldo-20261102T050000Z-1a2b3c4d.zip", "/respaldos/1"):
        assert client.get(ruta).status_code == 404
    reglas = [regla.rule for regla in flask_app.url_map.iter_rules() if "respaldo" in regla.rule]
    assert sorted(set(reglas)) == ["/api/respaldos", "/api/respaldos/<int:id_respaldo>/restaurar",
                              "/api/respaldos/<int:id_respaldo>/verificar", "/api/respaldos/estado"]


@pytest.mark.parametrize("ruta", ["/api/respaldos/abc/restaurar", "/api/respaldos/1.5/restaurar",
                                  "/api/respaldos/-1/restaurar", "/api/respaldos/1;DROP/restaurar",
                                  "/api/respaldos/../restaurar"])
def test_el_identificador_de_la_ruta_debe_ser_un_entero(client, iniciar_sesion, monkeypatch, ruta):
    prohibido = ServicioProhibido(monkeypatch)
    admin(iniciar_sesion)
    assert client.post(ruta, json=CUERPO_RESTAURAR).status_code in (404, 308)
    assert prohibido.llamadas == []


# ---------------------------------------------------------------------------
# Historial y estado
# ---------------------------------------------------------------------------

FILA = {
    "id_respaldo": 4, "operacion": "RESPALDO", "tipo": "MANUAL", "estado": "EXITOSO",
    "fecha_inicio": datetime.datetime(2026, 11, 2, 13, 5, 9), "fecha_fin": datetime.datetime(2026, 11, 2, 13, 5, 11),
    "duracion_segundos": Decimal("2.37"), "id_usuario": 1, "usuario": "Admin Ficticia", "id_relacionado": None,
    "nombre_archivo": "nahan-respaldo-20261102T160509Z-1a2b3c4d.zip", "tamano_bytes": 5685, "sha256": "ab" * 32,
    "detalle": "tablas=22, filas=22, adjuntos=1", "mensaje_error": None, "archivo_eliminado_en": None,
}


def test_el_historial_se_entrega_formateado(client, iniciar_sesion, monkeypatch, tmp_path):
    admin(iniciar_sesion)
    monkeypatch.setenv("RESPALDO_DIR", str(tmp_path))
    (tmp_path / FILA["nombre_archivo"]).write_bytes(b"x")
    capturado = {}

    def listar(self, limite):
        capturado["limite"] = limite
        return [FILA, {**FILA, "id_respaldo": 3, "tipo": "PROGRAMADO", "estado": "FALLIDO", "id_usuario": None,
                       "usuario": None, "fecha_fin": None, "duracion_segundos": None, "nombre_archivo": None,
                       "mensaje_error": "mysqldump falló", "detalle": None}]
    monkeypatch.setattr(servicio.RegistroMySQL, "listar", listar)

    respuesta = client.get("/api/respaldos")
    assert respuesta.status_code == 200 and capturado["limite"] == 20
    cuerpo = respuesta.get_json()
    assert cuerpo["limite"] == 20
    primero, segundo = cuerpo["respaldos"]
    assert primero["fecha_inicio"] == "2026-11-02 13:05:09" and primero["duracion_segundos"] == 2.37
    assert primero["archivo_disponible"] is True and primero["usuario"] == "Admin Ficticia"
    assert segundo["tipo"] == "PROGRAMADO" and segundo["estado"] == "FALLIDO"
    assert segundo["fecha_fin"] is None and segundo["archivo_disponible"] is False
    assert segundo["mensaje_error"] == "mysqldump falló"


def test_el_historial_no_expone_rutas_del_servidor(client, iniciar_sesion, monkeypatch, tmp_path):
    admin(iniciar_sesion)
    monkeypatch.setenv("RESPALDO_DIR", str(tmp_path))
    monkeypatch.setattr(servicio.RegistroMySQL, "listar", lambda self, limite: [FILA])
    texto = client.get("/api/respaldos").get_data(as_text=True)
    assert str(tmp_path) not in texto and "/" not in "".join(
        re.findall(r'"nombre_archivo":\s*"([^"]*)"', texto))


@pytest.mark.parametrize("limite", ["10", "20", "50", "100", " 10 "])
def test_limites_validos_del_historial(client, iniciar_sesion, monkeypatch, limite):
    admin(iniciar_sesion)
    usado = {}
    monkeypatch.setattr(servicio.RegistroMySQL, "listar", lambda self, n: usado.setdefault("n", n) and [])
    respuesta = client.get("/api/respaldos", query_string={"limite": limite})
    assert respuesta.status_code == 200 and usado["n"] == int(limite)


@pytest.mark.parametrize("limite", ["0", "-1", "abc", "5", "101", "1e2", "10.5", "²", "１０", "10;DROP", "'", "9" * 400])
def test_limites_invalidos_del_historial_se_rechazan(client, iniciar_sesion, monkeypatch, limite):
    prohibido = ServicioProhibido(monkeypatch)
    admin(iniciar_sesion)
    respuesta = client.get("/api/respaldos", query_string={"limite": limite})
    assert respuesta.status_code == 400 and "límite" in respuesta.get_json()["error"]
    assert prohibido.llamadas == []


def test_estado_resume_almacenamiento_y_ultimo_respaldo(client, iniciar_sesion, monkeypatch):
    admin(iniciar_sesion)
    monkeypatch.setattr(servicio, "estado_del_sistema", lambda: {
        "almacenamiento": {"directorio": "/mnt/respaldos", "apto": True, "independiente": False,
                           "verificaciones": [{"clave": "independencia", "nivel": "aviso", "mensaje": "mismo dispositivo"}]},
        "restauracion_habilitada": False, "base_de_destino": None, "retencion_maxima": 30, "operacion_en_curso": False,
        "ultimo_exitoso": {"id_respaldo": 4, "tipo": "PROGRAMADO", "fecha_inicio": FILA["fecha_inicio"],
                           "fecha_fin": FILA["fecha_fin"], "tamano_bytes": 5685},
    })
    cuerpo = client.get("/api/respaldos/estado").get_json()
    assert cuerpo["almacenamiento"]["independiente"] is False
    assert cuerpo["ultimo_exitoso"] == {"id_respaldo": 4, "tipo": "PROGRAMADO", "fecha_fin": "2026-11-02 13:05:11", "tamano_bytes": 5685}
    assert cuerpo["restauracion_habilitada"] is False and "systemd" in cuerpo["programacion"]


def test_estado_sin_respaldos_previos(client, iniciar_sesion, monkeypatch):
    admin(iniciar_sesion)
    monkeypatch.setattr(servicio, "estado_del_sistema", lambda: {
        "almacenamiento": {"directorio": "", "apto": False, "independiente": None, "verificaciones": []},
        "restauracion_habilitada": False, "base_de_destino": None, "retencion_maxima": 30,
        "operacion_en_curso": False, "ultimo_exitoso": None})
    assert client.get("/api/respaldos/estado").get_json()["ultimo_exitoso"] is None


# ---------------------------------------------------------------------------
# Respaldo manual (CA2) y su auditoría
# ---------------------------------------------------------------------------

RESULTADO = {"id_respaldo": 12, "nombre_archivo": "nahan-respaldo-20261102T160509Z-1a2b3c4d.zip",
             "tamano_bytes": 5685, "sha256": "cd" * 32, "detalle": "tablas=22", "manifiesto": {"x": 1}}


def test_el_administrador_ejecuta_un_respaldo_manual_y_queda_auditado(client, iniciar_sesion, monkeypatch, auditoria):
    admin(iniciar_sesion, usuario_id=9)
    llamadas = []
    monkeypatch.setattr(servicio, "ejecutar_respaldo", lambda tipo, id_usuario=None, **k: llamadas.append((tipo, id_usuario)) or RESULTADO)

    respuesta = client.post("/api/respaldos")
    assert respuesta.status_code == 201
    assert llamadas == [("MANUAL", 9)], "el usuario sale de la sesión, no de la solicitud"
    cuerpo = respuesta.get_json()["respaldo"]
    assert cuerpo["id_respaldo"] == 12 and cuerpo["sha256"] == "cd" * 32 and "manifiesto" not in cuerpo
    assert len(auditoria) == 1
    id_usuario, tabla, id_registro, accion, anteriores, nuevos = auditoria[0]
    assert (id_usuario, tabla, id_registro, accion, anteriores) == (9, "respaldo", 12, "RESPALDO_MANUAL", None)
    assert "nahan-respaldo-20261102T160509Z-1a2b3c4d.zip" in nuevos and "cd" * 32 in nuevos


def test_el_respaldo_manual_ignora_lo_que_envie_el_cliente(client, iniciar_sesion, monkeypatch, auditoria):
    admin(iniciar_sesion, usuario_id=9)
    llamadas = []
    monkeypatch.setattr(servicio, "ejecutar_respaldo", lambda tipo, id_usuario=None, **k: llamadas.append((tipo, id_usuario, k)) or RESULTADO)
    cuerpo = {"tipo": "PROGRAMADO", "id_usuario": 1, "ruta": "/etc", "directorio": "/tmp", "RESPALDO_DIR": "/tmp"}
    assert client.post("/api/respaldos", json=cuerpo).status_code == 201
    assert llamadas == [("MANUAL", 9, {})]


@pytest.mark.parametrize("excepcion,estado,codigo", [
    (servicio.AlmacenamientoNoValido("RESPALDO_DIR no está configurado"), 503, "ALMACENAMIENTO_NO_VALIDO"),
    (servicio.ErrorRespaldo("mysqldump falló (código 2): Access denied"), 500, "ERROR_RESPALDO"),
    (servicio.RespaldoNoValido("El respaldo no es válido: x"), 422, "RESPALDO_NO_VALIDO"),
])
def test_un_respaldo_fallido_responde_con_el_error_y_queda_auditado(client, iniciar_sesion, monkeypatch, auditoria, excepcion, estado, codigo):
    admin(iniciar_sesion, usuario_id=9)
    excepcion.id_respaldo = 31

    def falla(tipo, id_usuario=None, **k):
        raise excepcion
    monkeypatch.setattr(servicio, "ejecutar_respaldo", falla)

    respuesta = client.post("/api/respaldos")
    assert respuesta.status_code == estado
    cuerpo = respuesta.get_json()
    assert cuerpo["codigo"] == codigo and cuerpo["id_respaldo"] == 31 and cuerpo["error"] == excepcion.mensaje
    assert [(p[3], p[2]) for p in auditoria] == [("RESPALDO_MANUAL_FALLIDO", 31)]
    assert auditoria[0][5] == excepcion.mensaje


def test_un_respaldo_rechazado_por_otra_operacion_en_curso_responde_409_sin_auditar(client, iniciar_sesion, monkeypatch, auditoria):
    admin(iniciar_sesion)

    def ocupado(tipo, id_usuario=None, **k):
        raise servicio.OperacionEnCurso("Ya hay un respaldo o una restauración en curso.")
    monkeypatch.setattr(servicio, "ejecutar_respaldo", ocupado)
    respuesta = client.post("/api/respaldos")
    assert respuesta.status_code == 409 and respuesta.get_json()["codigo"] == "OPERACION_EN_CURSO"
    assert auditoria == []


def test_un_error_inesperado_no_filtra_detalles(client, iniciar_sesion, monkeypatch, auditoria):
    admin(iniciar_sesion)

    def explota(tipo, id_usuario=None, **k):
        raise RuntimeError("secreto-interno /ruta/privada")
    monkeypatch.setattr(servicio, "ejecutar_respaldo", explota)
    respuesta = client.post("/api/respaldos")
    assert respuesta.status_code == 500
    assert "secreto-interno" not in respuesta.get_data(as_text=True)


def test_si_falla_la_auditoria_el_respaldo_igual_se_informa(client, iniciar_sesion, monkeypatch):
    admin(iniciar_sesion)
    monkeypatch.setattr(servicio, "ejecutar_respaldo", lambda *a, **k: RESULTADO)

    def sin_base():
        raise RuntimeError("base caída")
    monkeypatch.setattr(rutas, "get_connection", sin_base)
    assert client.post("/api/respaldos").status_code == 201


# ---------------------------------------------------------------------------
# Verificación y restauración (CA4)
# ---------------------------------------------------------------------------

def test_verificar_un_respaldo(client, iniciar_sesion, monkeypatch):
    admin(iniciar_sesion)
    monkeypatch.setattr(servicio, "verificar_respaldo", lambda id_respaldo: {"tablas": 22, "filas": 40, "adjuntos": 2, "migraciones": None, "creado_utc": "x"})
    respuesta = client.post("/api/respaldos/7/verificar")
    assert respuesta.status_code == 200 and respuesta.get_json()["resumen"]["filas"] == 40


@pytest.mark.parametrize("excepcion,estado", [
    (servicio.RespaldoNoValido("El respaldo no es válido: SHA-256"), 422),
    (servicio.RespaldoNoEncontrado("El respaldo indicado no existe."), 404),
])
def test_verificar_informa_los_respaldos_dañados_o_inexistentes(client, iniciar_sesion, monkeypatch, excepcion, estado):
    admin(iniciar_sesion)

    def falla(id_respaldo):
        raise excepcion
    monkeypatch.setattr(servicio, "verificar_respaldo", falla)
    respuesta = client.post("/api/respaldos/7/verificar")
    assert respuesta.status_code == estado and respuesta.get_json()["error"] == excepcion.mensaje


@pytest.mark.parametrize("cuerpo", [
    None, [], "texto", 5, {}, {"password": "clave-correcta"},
    {"confirmacion": "restaurar", "password": "x"}, {"confirmacion": "RESTAURAR ", "password": "x"},
    {"confirmacion": "SI", "password": "x"}, {"confirmacion": None, "password": "x"}, {"confirmacion": ["RESTAURAR"], "password": "x"},
])
def test_la_restauracion_exige_una_confirmacion_exacta(client, iniciar_sesion, monkeypatch, cuerpo):
    prohibido = ServicioProhibido(monkeypatch)
    admin(iniciar_sesion)
    respuesta = client.post("/api/respaldos/7/restaurar", json=cuerpo) if cuerpo is not None \
        else client.post("/api/respaldos/7/restaurar")
    assert respuesta.status_code == 400
    assert prohibido.llamadas == []


@pytest.mark.parametrize("clave", [None, "", 123, ["x"], {"a": 1}, True])
def test_la_restauracion_exige_la_contrasena(client, iniciar_sesion, monkeypatch, clave):
    prohibido = ServicioProhibido(monkeypatch)
    admin(iniciar_sesion)
    respuesta = client.post("/api/respaldos/7/restaurar", json={"confirmacion": "RESTAURAR", "password": clave})
    # Los valores que no son texto los rechaza antes el filtro global de cuerpos JSON (app.py).
    assert respuesta.status_code == 400 and re.search("contraseña|password", respuesta.get_json()["error"])
    assert prohibido.llamadas == []


def test_una_contrasena_incorrecta_impide_restaurar(client, iniciar_sesion, monkeypatch, fake_connection_factory, auditoria):
    prohibido = ServicioProhibido(monkeypatch)
    admin(iniciar_sesion, usuario_id=3)
    consultas = []

    def handler(sql, params, cursor):
        if "password_hash" in sql:
            consultas.append(params)
            return [{"password_hash": hash_password("la-contraseña-real")}]
        return []
    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(rutas, "get_connection", lambda: conexion)

    respuesta = client.post("/api/respaldos/7/restaurar", json={"confirmacion": "RESTAURAR", "password": "otra-distinta"})
    assert respuesta.status_code == 403 and respuesta.get_json()["error"] == "La contraseña no es correcta."
    assert consultas == [(3,)] and prohibido.llamadas == []
    rechazo = [p for s, p in conexion.executed if "INSERT INTO auditoria" in s]
    assert [(p[0], p[1], p[2], p[3]) for p in rechazo] == [(3, "respaldo", 7, "RESTAURACION_RECHAZADA")]
    assert "otra-distinta" not in str(rechazo)


def test_una_contrasena_correcta_permite_restaurar(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    admin(iniciar_sesion, usuario_id=3)
    llamadas = []
    monkeypatch.setattr(servicio, "ejecutar_restauracion",
                        lambda id_respaldo, id_usuario=None, **k: llamadas.append((id_respaldo, id_usuario)) or
                        {"id_restauracion": 8, "id_respaldo": 7, "detalle": "ok", "id_previo": 9, "advertencias": ["aviso"]})
    registradas = []

    def handler(sql, params, cursor):
        if "INSERT INTO auditoria" in sql:
            registradas.append(params)
            return []
        return [{"password_hash": hash_password("clave-correcta")}]
    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(rutas, "get_connection", lambda: conexion)

    respuesta = client.post("/api/respaldos/7/restaurar", json=CUERPO_RESTAURAR)
    assert respuesta.status_code == 200 and llamadas == [(7, 3)]
    cuerpo = respuesta.get_json()
    assert cuerpo["id_restauracion"] == 8 and cuerpo["advertencias"] == ["aviso"]
    assert [(p[1], p[2], p[3]) for p in registradas] == [("respaldo", 8, "RESTAURACION_RESPALDO")]
    assert "respaldo=7" in registradas[0][5] and "copia_previa=9" in registradas[0][5]
    assert "clave-correcta" not in str(registradas) and "clave-correcta" not in respuesta.get_data(as_text=True)


@pytest.mark.parametrize("excepcion,estado,codigo", [
    (servicio.OperacionNoPermitida("La restauración está deshabilitada en este entorno"), 403, "OPERACION_NO_PERMITIDA"),
    (servicio.RespaldoNoEncontrado("El respaldo indicado no existe."), 404, "RESPALDO_NO_ENCONTRADO"),
    (servicio.RespaldoNoValido("El respaldo no es válido: SHA-256"), 422, "RESPALDO_NO_VALIDO"),
    (servicio.ErrorRespaldo("MySQL rechazó el volcado (error 1062)."), 500, "ERROR_RESPALDO"),
])
def test_los_errores_de_restauracion_se_informan_y_se_auditan(client, iniciar_sesion, monkeypatch, auditoria, excepcion, estado, codigo):
    admin(iniciar_sesion, usuario_id=3)
    monkeypatch.setattr(rutas, "_clave_valida", lambda id_usuario, clave: True)
    excepcion.id_respaldo = 15
    excepcion.recuperacion = "Se restableció automáticamente el estado anterior a la restauración."

    def falla(id_respaldo, id_usuario=None, **k):
        raise excepcion
    monkeypatch.setattr(servicio, "ejecutar_restauracion", falla)

    respuesta = client.post("/api/respaldos/7/restaurar", json=CUERPO_RESTAURAR)
    cuerpo = respuesta.get_json()
    assert respuesta.status_code == estado and cuerpo["codigo"] == codigo
    assert cuerpo["recuperacion"].startswith("Se restableció")
    assert [(p[3], p[2]) for p in auditoria] == [("RESTAURACION_FALLIDA", 15)]
    assert "respaldo=7" in auditoria[0][5]


def test_una_restauracion_simultanea_responde_409(client, iniciar_sesion, monkeypatch, auditoria):
    admin(iniciar_sesion)
    monkeypatch.setattr(rutas, "_clave_valida", lambda *a: True)

    def ocupado(*a, **k):
        raise servicio.OperacionEnCurso("Ya hay un respaldo o una restauración en curso.")
    monkeypatch.setattr(servicio, "ejecutar_restauracion", ocupado)
    assert client.post("/api/respaldos/7/restaurar", json=CUERPO_RESTAURAR).status_code == 409
    assert auditoria == []


def test_una_clave_sin_conexion_a_la_base_se_trata_como_incorrecta(client, iniciar_sesion, monkeypatch):
    prohibido = ServicioProhibido(monkeypatch)
    admin(iniciar_sesion)
    monkeypatch.setattr(rutas, "get_connection", lambda: None)
    assert client.post("/api/respaldos/7/restaurar", json=CUERPO_RESTAURAR).status_code == 403
    assert prohibido.llamadas == []


# ---------------------------------------------------------------------------
# Modo mantenimiento durante la restauración
# ---------------------------------------------------------------------------

def test_durante_una_restauracion_la_api_responde_503(client, iniciar_sesion, monkeypatch):
    monkeypatch.setattr(app_module, "restauracion_en_curso", lambda: True)
    for ruta in ("/api/auth/me", "/api/clientes", "/api/respaldos", "/api/tareas"):
        respuesta = client.get(ruta)
        assert respuesta.status_code == 503, ruta
        assert respuesta.headers["Retry-After"] == "60"
        assert respuesta.get_json()["codigo"] == "MANTENIMIENTO"
    assert client.post("/api/auth/login", json={"email": "a@b.cl", "password": "x"}).status_code == 503
    assert client.get("/").status_code == 200, "fuera de /api/ no hay bloqueo"


def test_sin_restauracion_en_curso_la_api_funciona_con_normalidad(client, iniciar_sesion, monkeypatch):
    monkeypatch.setattr(app_module, "restauracion_en_curso", lambda: False)
    admin(iniciar_sesion)
    monkeypatch.setattr(servicio.RegistroMySQL, "listar", lambda self, n: [])
    assert client.get("/api/respaldos").status_code == 200


# ---------------------------------------------------------------------------
# Compatibilidad con la auditoría (RF56/RF49)
# ---------------------------------------------------------------------------

def test_los_eventos_de_respaldo_pertenecen_al_modulo_respaldos():
    assert modulo_de_tabla("respaldo") == "Respaldos"
    assert "Respaldos" in modulos_disponibles()


def test_el_panel_de_cambios_recientes_acepta_el_modulo_respaldos(client, iniciar_sesion, fake_connection_factory, monkeypatch):
    import backend.routes.historial_routes as historial
    admin(iniciar_sesion)
    sentencias = []

    def handler(sql, params, cursor):
        sentencias.append((sql, params))
        return [{"id_auditoria": 1, "fecha": datetime.datetime(2026, 11, 2, 13, 5, 9), "usuario": "Admin Ficticia",
                 "tabla_afectada": "respaldo", "id_registro": 12, "accion": "RESPALDO_MANUAL",
                 "cliente_disponible": None, "tarea_disponible": None}]
    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(historial, "get_connection", lambda: conexion)

    respuesta = client.get("/api/cambios-recientes", query_string={"modulo": "Respaldos"})
    assert respuesta.status_code == 200
    cambio = respuesta.get_json()["cambios"][0]
    assert cambio["modulo"] == "Respaldos" and cambio["tipo"] == "RESPALDO_MANUAL"
    assert cambio["tipo_registro"] is None and cambio["id_registro"] is None
    assert sentencias[-1][1][0] == "respaldo"


# ---------------------------------------------------------------------------
# Interfaz
# ---------------------------------------------------------------------------

def leer(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as archivo:
        return archivo.read()


def test_la_pagina_de_respaldos_solo_la_ve_un_administrador_y_usa_los_estilos_del_sistema():
    html = leer("frontend", "respaldos", "respaldos.html")
    assert 'protegerPagina(["ADMINISTRADOR"])' in html and 'cargarNavegacion("respaldos")' in html
    for hoja in ("variables", "global", "buttons", "forms", "cards", "tables", "badges", "navigation", "topbar"):
        assert f"../assets/css/{hoja}.css" in html
    for script in re.findall(r'<script src="([^"]+)"', html):
        assert os.path.exists(os.path.normpath(os.path.join(RAIZ, "frontend", "respaldos", script))), script
    assert 'id="seccionRestaurar" hidden' in html, "el formulario de restauración empieza oculto"


def test_el_menu_de_administracion_incluye_respaldos():
    navegacion = leer("frontend", "assets", "js", "navigation.js")
    admin_items = navegacion[navegacion.index("const ADMIN_ITEMS"):]
    assert 'id: "respaldos"' in admin_items and '../respaldos/respaldos.html' in admin_items
    assert 'id: "respaldos"' not in navegacion[:navegacion.index("const ADMIN_ITEMS")]


def test_el_javascript_de_respaldos_no_inserta_html_ni_usa_eval():
    js = leer("frontend", "respaldos", "respaldos.js")
    for prohibido in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert prohibido not in js
    assert js.count("fetch(") == 1, "una sola función se comunica con el servidor"
    assert "credentials: window.API_CONFIG.credentials" in js


def test_las_solicitudes_post_de_la_interfaz_envian_un_cuerpo_json():
    """El backend rechaza «Content-Type: application/json» sin cuerpo (validar_cuerpo_json)."""
    js = leer("frontend", "respaldos", "respaldos.js")
    posts = re.findall(r'method: "POST",\s*headers: \{ "Content-Type": "application/json" \},\s*body: JSON\.stringify\(([^)]*\)?)\)', js)
    assert len(posts) == js.count('method: "POST"') == 3
    assert posts.count("{}") == 2 and any("confirmacion" in p and "password" in p for p in posts)


def test_la_interfaz_pide_la_confirmacion_antes_de_cada_operacion_critica():
    js = leer("frontend", "respaldos", "respaldos.js")
    assert 'await confirmarAccion("¿Ejecutar un respaldo ahora?' in js, "RF67: confirmación propia, ya no el confirm() nativo"
    assert 'confirmacion !== "RESTAURAR"' in js
    assert 'document.getElementById("inputClave").value = ""' in js, "la contraseña se borra tras enviarla"
    assert "localStorage" not in js and "sessionStorage" not in js


def test_los_botones_de_restaurar_solo_aparecen_con_la_restauracion_habilitada():
    js = leer("frontend", "respaldos", "respaldos.js")
    assert "if (restauracionHabilitada)" in js and "respaldo.archivo_disponible" in js


# ---------------------------------------------------------------------------
# Programación y despliegue (CA1)
# ---------------------------------------------------------------------------

def test_el_temporizador_ejecuta_un_respaldo_diario_y_recupera_los_omitidos():
    timer = leer("deploy", "systemd", "nahan-respaldo.timer")
    assert re.search(r"^OnCalendar=\*-\*-\* \d\d:\d\d:\d\d$", timer, re.M)
    assert "Persistent=true" in timer and "WantedBy=timers.target" in timer


def test_el_servicio_de_respaldo_es_un_proceso_unico_con_permisos_restringidos():
    unidad = leer("deploy", "systemd", "nahan-respaldo.service")
    assert "Type=oneshot" in unidad
    assert "python -m backend.respaldos_programados" in unidad
    assert "EnvironmentFile=" in unidad and "UMask=0077" in unidad
    assert "User=ubuntu" in unidad and "User=root" not in unidad
    assert "Nice=19" in unidad and "IOSchedulingClass=idle" in unidad
    assert "password" not in unidad.lower()


def test_las_unidades_de_respaldo_siguen_el_patron_de_las_de_vencimientos():
    base = leer("deploy", "systemd", "nahan-vencimientos.service")
    unidad = leer("deploy", "systemd", "nahan-respaldo.service")
    for linea in ("User=ubuntu", "Group=www-data", "WorkingDirectory=/var/www/nahan-asesores-sistema",
                  "EnvironmentFile=/var/www/nahan-asesores-sistema/.env"):
        assert linea in base and linea in unidad


_DIRECTIVAS_CONOCIDAS = {
    "Unit": {"Description", "After", "Requires", "Wants"},
    "Service": {"Type", "User", "Group", "WorkingDirectory", "EnvironmentFile", "UMask", "Nice", "IOSchedulingClass",
                "TimeoutStartSec", "ExecStart", "Restart", "RestartSec"},
    "Timer": {"OnCalendar", "Persistent", "Unit"},
    "Install": {"WantedBy"},
}


def _directivas(unidad):
    """Lee una unidad sin systemd: {sección: [(clave, valor)]}. Falla ante líneas que systemd rechazaría."""
    secciones, actual = {}, None
    for numero, linea in enumerate(unidad.splitlines(), 1):
        linea = linea.strip()
        if not linea or linea.startswith(("#", ";")):
            continue
        cabecera = re.fullmatch(r"\[([A-Za-z]+)\]", linea)
        if cabecera:
            actual = cabecera.group(1)
            secciones.setdefault(actual, [])
            continue
        clave, separador, valor = linea.partition("=")
        assert actual and separador and clave.isidentifier(), f"línea {numero} no es una directiva válida: {linea!r}"
        secciones[actual].append((clave, valor))
    return secciones


@pytest.mark.parametrize("archivo", ["nahan-respaldo.service", "nahan-respaldo.timer"])
def test_las_unidades_de_respaldo_solo_usan_directivas_conocidas(archivo):
    """Comprobación ESTÁTICA (no hay systemd en el entorno de pruebas): detecta claves mal escritas o secciones inválidas.

    No reemplaza `systemd-analyze verify` ni un ciclo real del temporizador, que quedan documentados como pendientes en AWS.
    """
    secciones = _directivas(leer("deploy", "systemd", archivo))
    assert set(secciones) <= set(_DIRECTIVAS_CONOCIDAS)
    for seccion, directivas in secciones.items():
        claves = [clave for clave, _ in directivas]
        assert set(claves) <= _DIRECTIVAS_CONOCIDAS[seccion], f"{archivo}: directiva desconocida en [{seccion}]"
        assert len(claves) == len(set(claves)), f"{archivo}: directiva repetida en [{seccion}]"


def test_el_temporizador_activa_la_unidad_de_respaldo_y_usa_rutas_absolutas():
    servicio = dict(_directivas(leer("deploy", "systemd", "nahan-respaldo.service"))["Service"])
    timer = _directivas(leer("deploy", "systemd", "nahan-respaldo.timer"))
    assert "Unit" not in dict(timer["Timer"]), "sin Unit=, systemd activa nahan-respaldo.service por tener el mismo nombre"
    assert servicio["ExecStart"].startswith("/") and servicio["WorkingDirectory"].startswith("/")
    assert servicio["EnvironmentFile"].startswith("/") and not servicio["EnvironmentFile"].startswith("-"), \
        "sin el prefijo «-» el servicio falla si falta el .env, en vez de respaldar con valores por defecto"
    assert int(servicio["TimeoutStartSec"]) >= 600


def _leer_como_systemd(ruta):
    """Reglas de EnvironmentFile= (systemd.exec): «#» o «;» al inicio comentan, sin comentarios al final de la línea."""
    valores = {}
    for linea in open(ruta, encoding="utf-8").read().splitlines():
        linea = linea.strip()
        if not linea or linea[0] in "#;":
            continue
        clave, _, valor = linea.partition("=")
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        valores[clave.strip()] = valor
    return valores


def test_el_env_de_ejemplo_se_lee_igual_con_systemd_y_con_dotenv():
    """El servicio de respaldo carga .env con EnvironmentFile=; la aplicación, con python-dotenv. Si un valor
    llevara un comentario al final de la línea, systemd lo conservaría completo y dotenv no."""
    from dotenv import dotenv_values
    ruta = os.path.join(RAIZ, ".env.example")
    con_dotenv = {k: v or "" for k, v in dotenv_values(ruta).items()}
    assert _leer_como_systemd(ruta) == con_dotenv


def test_gunicorn_admite_operaciones_largas_de_respaldo():
    assert re.search(r"--timeout (\d+)", leer("deploy", "systemd", "nahan.service")).group(1) == "300"


def test_el_modulo_programado_se_puede_importar_y_tiene_una_interfaz_estable():
    from backend import respaldos_programados as cli
    assert (cli.SALIDA_OK, cli.SALIDA_ERROR, cli.SALIDA_OCUPADO) == (0, 1, 75)
    parser = cli.crear_parser()
    assert parser.parse_args([]).comando is None
    assert parser.parse_args(["restaurar", "--id", "3", "--confirmo-base", "x"]).id == 3
    with pytest.raises(SystemExit):
        parser.parse_args(["restaurar", "--confirmo-base", "x"])
    with pytest.raises(SystemExit):
        parser.parse_args(["restaurar", "--id", "3", "--archivo", "a.zip", "--confirmo-base", "x"])
    with pytest.raises(SystemExit):
        parser.parse_args(["respaldar", "--tipo", "previo"])


def test_el_ejemplo_de_entorno_documenta_rf60_sin_secretos():
    ejemplo = leer(".env.example")
    for variable in ("RESPALDO_DIR", "RESPALDO_RETENCION_MAXIMA", "RESPALDO_EXIGIR_DISPOSITIVO_SEPARADO",
                     "RESTAURACION_HABILITADA", "RESTAURACION_DB_NAME", "MYSQLDUMP_BIN"):
        assert re.search(rf"^{variable}=", ejemplo, re.M), variable
    assert re.search(r"^RESTAURACION_HABILITADA=false$", ejemplo, re.M)
    for variable in ("RESPALDO_DIR", "RESPALDO_DB_USER", "RESPALDO_DB_PASSWORD", "RESTAURACION_DB_USER", "RESTAURACION_DB_PASSWORD"):
        assert re.search(rf"^{variable}=$", ejemplo, re.M), f"{variable} debe ir vacía en el ejemplo"


def test_el_codigo_de_rf60_no_contiene_credenciales_escritas_a_mano():
    for ruta in (("backend", "utils", "respaldos.py"), ("backend", "routes", "respaldos_routes.py"),
                 ("backend", "respaldos_programados.py"), ("frontend", "respaldos", "respaldos.js")):
        texto = leer(*ruta)
        assert not re.search(r"""(password|passwd|secret|token)\s*=\s*["'][^"'{]+["']""", texto, re.I), ruta
        assert not re.search(r"AKIA[0-9A-Z]{16}", texto), ruta


def test_rf60_no_agrega_dependencias():
    with open(os.path.join(RAIZ, "requirements.txt"), encoding="utf-8") as archivo:
        paquetes = {l.split("==")[0].strip().lower() for l in archivo if l.strip()}
    assert not paquetes & {"boto3", "apscheduler", "celery", "schedule", "paramiko", "sqlalchemy"}


# ---------------------------------------------------------------------------
# Límite de intentos de la contraseña de confirmación
# ---------------------------------------------------------------------------

def test_tras_cinco_confirmaciones_rechazadas_la_restauracion_se_bloquea(client, iniciar_sesion, monkeypatch, auditoria):
    prohibido = ServicioProhibido(monkeypatch)
    admin(iniciar_sesion, usuario_id=3)
    monkeypatch.setattr(rutas, "_confirmaciones_rechazadas_recientes", lambda id_usuario: rutas.MAX_CONFIRMACIONES_RECHAZADAS)
    monkeypatch.setattr(rutas, "_clave_valida", lambda *a: pytest.fail("no debe comprobar la contraseña bloqueado"))

    respuesta = client.post("/api/respaldos/7/restaurar", json=CUERPO_RESTAURAR)
    assert respuesta.status_code == 429 and respuesta.get_json()["codigo"] == "DEMASIADOS_INTENTOS"
    assert respuesta.headers["Retry-After"] == "900"
    assert prohibido.llamadas == [] and auditoria == []


@pytest.mark.parametrize("rechazadas", [0, 1, 4])
def test_por_debajo_del_limite_se_sigue_comprobando_la_contrasena(client, iniciar_sesion, monkeypatch, auditoria, rechazadas):
    admin(iniciar_sesion, usuario_id=3)
    monkeypatch.setattr(rutas, "_confirmaciones_rechazadas_recientes", lambda id_usuario: rechazadas)
    monkeypatch.setattr(rutas, "_clave_valida", lambda *a: False)
    assert client.post("/api/respaldos/7/restaurar", json=CUERPO_RESTAURAR).status_code == 403
    assert [p[3] for p in auditoria] == ["RESTAURACION_RECHAZADA"]


def test_si_no_se_puede_contar_el_limite_la_restauracion_se_rechaza(client, iniciar_sesion, monkeypatch):
    """Falla cerrada: sin saber cuántos intentos hubo, no se comprueba la contraseña ni se restaura."""
    prohibido = ServicioProhibido(monkeypatch)
    admin(iniciar_sesion)
    monkeypatch.setattr(rutas, "_confirmaciones_rechazadas_recientes", lambda id_usuario: None)
    monkeypatch.setattr(rutas, "_clave_valida", lambda *a: pytest.fail("no debe comprobar la contraseña"))
    assert client.post("/api/respaldos/7/restaurar", json=CUERPO_RESTAURAR).status_code == 503
    assert prohibido.llamadas == []


def test_el_conteo_de_rechazos_es_por_usuario_y_por_ventana(monkeypatch, fake_connection_factory):
    monkeypatch.undo()
    capturado = []

    def handler(sql, params, cursor):
        capturado.append((" ".join(sql.split()), params))
        return [{"n": 4}]
    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(rutas, "get_connection", lambda: conexion)
    assert rutas._confirmaciones_rechazadas_recientes(9) == 4
    consulta, parametros = capturado[0]
    assert "WHERE id_usuario = %s AND tabla_afectada = %s AND accion = %s" in consulta
    assert "DATE_SUB(NOW(), INTERVAL %s MINUTE)" in consulta
    assert parametros == (9, "respaldo", "RESTAURACION_RECHAZADA", 15)

    monkeypatch.setattr(rutas, "get_connection", lambda: None)
    assert rutas._confirmaciones_rechazadas_recientes(9) is None


@pytest.mark.parametrize("valor", [None, "", "false", "False", "0", "no", "off", "talvez", " "])
def test_la_restauracion_solo_se_habilita_con_un_valor_afirmativo_explicito(valor):
    entorno = {} if valor is None else {"RESTAURACION_HABILITADA": valor}
    assert servicio.ConfigRespaldo(entorno).restauracion_habilitada is False


@pytest.mark.parametrize("valor", ["true", "True", "1", "yes", "on", " TRUE "])
def test_valores_afirmativos_habilitan_la_restauracion(valor):
    assert servicio.ConfigRespaldo({"RESTAURACION_HABILITADA": valor}).restauracion_habilitada is True


def test_la_pantalla_explica_que_la_restauracion_no_esta_disponible_y_oculta_el_boton():
    js = leer("frontend", "respaldos", "respaldos.js")
    assert "No disponible: la restauración está deshabilitada en este entorno" in js
    assert "if (restauracionHabilitada)" in js, "el botón Restaurar solo se crea con la función habilitada"
