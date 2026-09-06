import logging

from flask import Blueprint, request, jsonify, session
from backend.config.db import get_connection
from backend.utils.auth import login_required, obtener_usuario_actual
from backend.utils.security import check_password

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

@auth_bp.route("/login", methods=["POST"])
def login():
    connection = None
    cursor = None
    data = request.get_json()

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({
            "error": "Correo y contraseña son obligatorios"
        }), 400

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        sql = """
            SELECT
                u.id_usuario,
                u.nombres,
                u.email,
                u.password_hash,
                u.estado,
                u.id_rol,
                r.nombre_rol,
                u.id_area,
                a.nombre_area
            FROM usuario u
            INNER JOIN rol r ON u.id_rol = r.id_rol
            INNER JOIN area a ON u.id_area = a.id_area
            WHERE u.email = %s
        """

        cursor.execute(sql, (email,))
        usuario = cursor.fetchone()

        if not usuario:
            return jsonify({
                "error": "Credenciales incorrectas"
            }), 401

        if usuario["estado"] != "ACTIVO":
            return jsonify({
                "error": "Usuario inactivo. Contacte al administrador."
            }), 403

        password_valida = check_password(password, usuario["password_hash"])

        if not password_valida:
            return jsonify({
                "error": "Credenciales incorrectas"
            }), 401

        session.clear()
        session.permanent = True
        session["usuario_id"] = usuario["id_usuario"]
        session["rol_id"] = usuario["id_rol"]
        session["area_id"] = usuario["id_area"]
        session["nombre"] = usuario["nombres"]

        usuario.pop("password_hash")

        return jsonify({
            "message": "Inicio de sesión correcto",
            "usuario": usuario
        }), 200

    except Exception:
        logger.exception("Error al iniciar sesión")
        return jsonify({
            "error": "Error interno al iniciar sesión"
        }), 500

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


@auth_bp.route("/auth/me", methods=["GET"])
@login_required
def auth_me():
    usuario = obtener_usuario_actual()

    return jsonify({
        "usuario": usuario,
        "permisos": {
            "es_admin": usuario["nombre_rol"] == "ADMINISTRADOR"
        }
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()

    return jsonify({
        "message": "Sesión cerrada correctamente"
    }), 200
