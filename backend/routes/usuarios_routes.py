from flask import Blueprint, request, jsonify
from backend.config.db import get_connection
from backend.utils.security import hash_password

usuarios_bp = Blueprint("usuarios", __name__)

@usuarios_bp.route("/usuarios", methods=['POST'])
def create_usuario():
    data = request.get_json()

    id_rol = data.get("id_rol")
    id_area = data.get("id_area")
    nombres = data.get("nombres")
    email = data.get("email")
    password = data.get("password")

    if not id_rol or not id_area or not nombres or not email or not password:
        return jsonify({"error": "Todos los campos son obligatorios"}), 400
    
    password_hash = hash_password(password)

    try:
        connection = get_connection()
        cursor = connection.cursor()

        sql = """INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash)
                 VALUES (%s, %s, %s, %s, %s)"""
        
        values = (id_rol, id_area, nombres, email, password_hash)

        cursor.execute(sql, values)
        connection.commit()

        return jsonify({"message": "Usuario registrado correctamente"}), 201
    
    except Exception as e:
        return jsonify({"error": str(e)}), 600
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


