from flask import Blueprint, request, jsonify
from backend.config.db import get_connection
from backend.utils.security import check_password

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["POST"])
def login():
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

        usuario.pop("password_hash")

        return jsonify({
            "message": "Inicio de sesión correcto",
            "usuario": usuario
        }), 200

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()