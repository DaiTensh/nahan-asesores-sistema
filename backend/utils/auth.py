import logging
import time
from functools import wraps

from flask import g, jsonify, request, session

from backend.config.db import get_connection


logger = logging.getLogger(__name__)

ROLES = {
    1: "ADMINISTRADOR",
    2: "USUARIO_AREA_JURIDICA",
    3: "USUARIO_AREA_CONTABLE",
}

ROL_ADMINISTRADOR = "ADMINISTRADOR"
ROL_JURIDICA = "USUARIO_AREA_JURIDICA"
ROL_CONTABLE = "USUARIO_AREA_CONTABLE"
ROLES_OPERATIVOS = (ROL_ADMINISTRADOR, ROL_JURIDICA, ROL_CONTABLE)

# ---------------------------------------------------------------------------
# RF59 — Cerrando Automático por Inactividad
# ---------------------------------------------------------------------------
# La sesión guarda la hora de la última actividad del usuario. Si entre dos
# solicitudes pasa más tiempo que el configurado por el administrador
# (parametros_sistema.SESION_INACTIVIDAD_MINUTOS), la sesión se invalida y la
# API responde 401 con codigo SESION_EXPIRADA.
#
# Las solicitudes automáticas del frontend (consultas periódicas, avisos) no
# son actividad del usuario: se marcan con la cabecera `X-Actividad: pasiva`
# y no renuevan el plazo. PERMANENT_SESSION_LIFETIME sigue siendo el tope
# absoluto de la sesión.

PARAMETRO_INACTIVIDAD = "SESION_INACTIVIDAD_MINUTOS"
PARAMETRO_AVISO = "SESION_AVISO_SEGUNDOS"
INACTIVIDAD_MINUTOS_DEFECTO = 30
AVISO_SEGUNDOS_DEFECTO = 60
INACTIVIDAD_MINUTOS_RANGO = (5, 240)
AVISO_SEGUNDOS_RANGO = (15, 600)
CABECERA_ACTIVIDAD = "X-Actividad"
CODIGO_SESION_EXPIRADA = "SESION_EXPIRADA"

_CACHE_CONFIG_SEGUNDOS = 30
_cache_config_sesion = {"valor": None, "leido": 0.0}


def _leer_parametro_entero(cursor, nombre, defecto, minimo, maximo):
    cursor.execute(
        "SELECT valor_parametro FROM parametros_sistema WHERE nombre_parametro = %s",
        (nombre,),
    )
    fila = cursor.fetchone()
    valor = fila.get("valor_parametro") if isinstance(fila, dict) else (fila[0] if fila else None)
    try:
        valor = int(valor)
    except (TypeError, ValueError):
        return defecto
    return valor if minimo <= valor <= maximo else defecto


def obtener_config_sesion():
    """Devuelve (minutos_inactividad, segundos_aviso), cacheados unos segundos
    para no consultar MySQL en cada solicitud. Ante cualquier problema de
    lectura se usan los valores por defecto."""
    ahora = time.time()
    if _cache_config_sesion["valor"] and ahora - _cache_config_sesion["leido"] < _CACHE_CONFIG_SEGUNDOS:
        return _cache_config_sesion["valor"]

    valor = (INACTIVIDAD_MINUTOS_DEFECTO, AVISO_SEGUNDOS_DEFECTO)
    connection = None
    cursor = None
    try:
        connection = get_connection()
        if connection is not None:
            cursor = connection.cursor(dictionary=True)
            valor = (
                _leer_parametro_entero(cursor, PARAMETRO_INACTIVIDAD, INACTIVIDAD_MINUTOS_DEFECTO,
                                       *INACTIVIDAD_MINUTOS_RANGO),
                _leer_parametro_entero(cursor, PARAMETRO_AVISO, AVISO_SEGUNDOS_DEFECTO,
                                       *AVISO_SEGUNDOS_RANGO),
            )
    except Exception:
        logger.warning("No se pudo leer la configuración de sesión; se usan los valores por defecto")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    _cache_config_sesion["valor"] = valor
    _cache_config_sesion["leido"] = ahora
    return valor


def invalidar_cache_config_sesion():
    _cache_config_sesion["valor"] = None


# Rutas que por definición no son actividad del usuario, aunque el
# frontend olvide la cabecera.
ENDPOINTS_PASIVOS = {"auth.estado_sesion"}


def es_solicitud_pasiva():
    return (
        request.endpoint in ENDPOINTS_PASIVOS
        or request.headers.get(CABECERA_ACTIVIDAD, "").strip().lower() == "pasiva"
    )


def marcar_actividad():
    session["ultima_actividad"] = time.time()


def segundos_restantes_sesion():
    minutos, _ = obtener_config_sesion()
    ultima = session.get("ultima_actividad") or time.time()
    return max(0, int(minutos * 60 - (time.time() - ultima)))


def _cerrar_sesion_por_inactividad(usuario_id):
    """Invalida la sesión y deja constancia en AUDITORIA."""
    session.clear()
    g._sesion_expirada = True

    connection = None
    cursor = None
    try:
        from backend.utils.auditoria import registrar_auditoria

        connection = get_connection()
        if connection is None:
            return
        cursor = connection.cursor()
        registrar_auditoria(cursor, usuario_id, "sesion", "CIERRE_INACTIVIDAD", id_registro=usuario_id)
        connection.commit()
    except Exception:
        logger.exception("No se pudo registrar el cierre de sesión por inactividad")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def obtener_usuario_actual():
    """Resuelve el usuario autenticado consultando su estado y rol
    directamente en la base de datos en cada solicitud.

    Solo se confía en `session["usuario_id"]` como clave de búsqueda; el
    resto de los datos (estado, rol, área) se leen frescos desde la BD para
    que un cambio de rol o una desactivación de cuenta surtan efecto de
    inmediato, sin esperar a que la sesión antigua expire.

    El resultado se memoriza en `flask.g` durante la solicitud: la mayoría
    de las rutas la invocan dos veces (una vez a través de los decoradores
    `login_required`/`roles_required` y otra vez dentro del propio handler
    para obtener el usuario actual), y sin este cacheo cada solicitud
    hacía dos consultas idénticas a MySQL en vez de una.
    """
    if hasattr(g, "_usuario_actual"):
        return g._usuario_actual

    usuario_id = session.get("usuario_id")

    if not usuario_id:
        g._usuario_actual = None
        return None

    # RF59: la sesión caduca si el usuario estuvo inactivo más del límite.
    ultima_actividad = session.get("ultima_actividad")
    if ultima_actividad is not None:
        minutos, _ = obtener_config_sesion()
        if time.time() - float(ultima_actividad) > minutos * 60:
            _cerrar_sesion_por_inactividad(usuario_id)
            g._usuario_actual = None
            return None

    connection = None
    cursor = None

    try:
        connection = get_connection()

        if connection is None:
            g._usuario_actual = None
            return None

        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                u.id_usuario,
                u.nombres,
                u.estado,
                u.id_rol,
                r.nombre_rol,
                u.id_area
            FROM usuario u
            INNER JOIN rol r ON u.id_rol = r.id_rol
            WHERE u.id_usuario = %s
            """,
            (usuario_id,)
        )
        usuario = cursor.fetchone()

        if not usuario or usuario["estado"] != "ACTIVO":
            g._usuario_actual = None
            return None

        if ultima_actividad is None or not es_solicitud_pasiva():
            marcar_actividad()

        g._usuario_actual = {
            "id_usuario": usuario["id_usuario"],
            "nombres": usuario["nombres"],
            "id_rol": usuario["id_rol"],
            "nombre_rol": usuario["nombre_rol"],
            "id_area": usuario["id_area"],
        }
        return g._usuario_actual
    except Exception:
        logger.exception("Error al resolver el usuario actual")
        g._usuario_actual = None
        return None
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def usuario_tiene_rol(usuario, roles_permitidos):
    return bool(usuario and usuario.get("nombre_rol") in roles_permitidos)


def respuesta_no_autenticado():
    if g.get("_sesion_expirada"):
        return jsonify({
            "error": "La sesión se cerró por inactividad",
            "codigo": CODIGO_SESION_EXPIRADA,
        }), 401
    return jsonify({"error": "No autenticado"}), 401


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not obtener_usuario_actual():
            return respuesta_no_autenticado()

        return func(*args, **kwargs)

    return wrapper


def roles_required(*roles_permitidos):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            usuario = obtener_usuario_actual()

            if not usuario:
                return respuesta_no_autenticado()

            if not usuario_tiene_rol(usuario, roles_permitidos):
                return jsonify({"error": "No tiene permisos para acceder a este recurso"}), 403

            return func(*args, **kwargs)

        return wrapper

    return decorator
