from functools import wraps

from flask import jsonify, session


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
    usuario_id = session.get("usuario_id")
    rol_id = session.get("rol_id")
    area_id = session.get("area_id")
    nombre = session.get("nombre")

    nombre_rol = ROLES.get(rol_id)

    if not usuario_id or not rol_id or not nombre_rol:
        return None

    return {
        "id_usuario": usuario_id,
        "nombres": nombre,
        "id_rol": rol_id,
        "nombre_rol": nombre_rol,
        "id_area": area_id,
    }


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
