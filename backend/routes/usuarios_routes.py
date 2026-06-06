from flask import Blueprint, request, jsonify
from backend.config.db import get_connection
from backend.utils.security import hash_password

usuarios_bp = Blueprint("usuarios", __name__)
#Usuarios
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


#Lista de usuarios
@usuarios_bp.route("/usuarios", methods=["GET"])
def listar_usuarios():
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        sql = """
            SELECT 
                u.id_usuario,
                u.nombres,
                u.email,
                u.estado,
                u.fecha_creacion,
                r.nombre_rol,
                a.nombre_area
            FROM usuario u
            INNER JOIN rol r ON u.id_rol = r.id_rol
            INNER JOIN area a ON u.id_area = a.id_area
            ORDER BY u.id_usuario DESC
        """

        cursor.execute(sql)
        usuarios = cursor.fetchall()

        return jsonify(usuarios), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

#Obtener usuario
@usuarios_bp.route("/usuarios/<int:id_usuario>", methods=["GET"])
def obtener_usuario(id_usuario):
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        sql = """
            SELECT
                u.id_usuario,
                u.id_rol,
                u.id_area,
                u.nombres,
                u.email,
                u.estado,
                u.fecha_creacion,
                r.nombre_rol,
                a.nombre_area
            FROM usuario u
            INNER JOIN rol r ON u.id_rol = r.id_rol
            INNER JOIN area a ON u.id_area = a.id_area
            WHERE u.id_usuario = %s
        """

        cursor.execute(sql, (id_usuario,))
        usuario = cursor.fetchone()

        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        return jsonify(usuario), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

#Actualizar usuario
@usuarios_bp.route("/usuarios/<int:id_usuario>", methods=["PUT"])
def actualizar_usuario(id_usuario):
    data = request.get_json()

    id_rol = data.get("id_rol")
    id_area = data.get("id_area")
    nombres = data.get("nombres")
    email = data.get("email")
    estado = data.get("estado")

    if not id_rol or not id_area or not nombres or not email or not estado:
        return jsonify({
            "error": "Todos los campos son obligatorios"
        }), 400

    try:
        connection = get_connection()
        cursor = connection.cursor()

        sql = """
            UPDATE usuario
            SET
                id_rol = %s,
                id_area = %s,
                nombres = %s,
                email = %s,
                estado = %s
            WHERE id_usuario = %s
        """

        values = (
            id_rol,
            id_area,
            nombres,
            email,
            estado,
            id_usuario
        )

        cursor.execute(sql, values)
        connection.commit()

        if cursor.rowcount == 0:
            return jsonify({
                "error": "Usuario no encontrado"
            }), 404

        return jsonify({
            "message": "Usuario actualizado correctamente"
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


#Desactivar usuario
@usuarios_bp.route("/usuarios/<int:id_usuario>/desactivar", methods=["PUT"])
def desactivar_usuario(id_usuario):
    try:
        connection = get_connection()
        cursor = connection.cursor()

        sql = """
            UPDATE usuario
            SET estado = 'INACTIVO'
            WHERE id_usuario = %s
        """

        cursor.execute(sql, (id_usuario,))
        connection.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Usuario no encontrado"}), 404

        return jsonify({
            "message": "Usuario deshabilitado correctamente"
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


#Asignar rol a usuario
@usuarios_bp.route("/usuarios/<int:id_usuario>/rol", methods=["PUT"])
def asignar_rol_usuario(id_usuario):
    data = request.get_json()

    id_rol = data.get("id_rol")

    if not id_rol:
        return jsonify({"error": "Debe seleccionar un rol"}), 400

    try:
        connection = get_connection()
        cursor = connection.cursor()

        sql = """
            UPDATE usuario
            SET id_rol = %s
            WHERE id_usuario = %s
        """

        cursor.execute(sql, (id_rol, id_usuario))
        connection.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Usuario no encontrado"}), 404

        return jsonify({
            "message": "Rol asignado correctamente"
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()