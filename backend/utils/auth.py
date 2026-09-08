import logging
from functools import wraps

from flask import g, jsonify, session

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


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not obtener_usuario_actual():
            return jsonify({"error": "No autenticado"}), 401

        return func(*args, **kwargs)

    return wrapper


def roles_required(*roles_permitidos):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            usuario = obtener_usuario_actual()

            if not usuario:
                return jsonify({"error": "No autenticado"}), 401

            if not usuario_tiene_rol(usuario, roles_permitidos):
                return jsonify({"error": "No tiene permisos para acceder a este recurso"}), 403

            return func(*args, **kwargs)

        return wrapper

    return decorator
