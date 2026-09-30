import logging

from mysql.connector import IntegrityError

from flask import Blueprint, request, jsonify
from backend.config.db import get_connection
from backend.utils.auditoria import registrar_auditoria
from backend.utils.auth import ROL_ADMINISTRADOR, login_required, obtener_usuario_actual, roles_required
from backend.utils.security import hash_password

usuarios_bp = Blueprint("usuarios", __name__)
logger = logging.getLogger(__name__)

ROL_ID_ADMINISTRADOR = 1
ROL_USUARIO_AREA_JURIDICA = 2
ROL_USUARIO_AREA_CONTABLE = 3

AREA_JURIDICA = 1
AREA_CONTABLE = 2
AREA_ADMINISTRACION = 3

AREA_POR_ROL = {
    ROL_ID_ADMINISTRADOR: AREA_ADMINISTRACION,
    ROL_USUARIO_AREA_JURIDICA: AREA_JURIDICA,
    ROL_USUARIO_AREA_CONTABLE: AREA_CONTABLE,
}

NOMBRE_AREA_POR_ROL = {
    ROL_ID_ADMINISTRADOR: "Ambas áreas",
    ROL_USUARIO_AREA_JURIDICA: "Área jurídica",
    ROL_USUARIO_AREA_CONTABLE: "Área contable",
}


def resolver_area_para_rol(id_rol, id_area=None, validar_area=True):
    try:
        id_rol = int(id_rol)
        id_area = int(id_area) if id_area not in (None, "") else None
    except (TypeError, ValueError):
        return None, None, "El rol o área seleccionada no es válida"

    area_esperada = AREA_POR_ROL.get(id_rol)

    if not area_esperada:
        return None, None, "El rol seleccionado no es válido"

    if id_rol == ROL_ID_ADMINISTRADOR:
        return id_rol, area_esperada, None

    if validar_area and id_area != area_esperada:
        nombre_area = NOMBRE_AREA_POR_ROL[id_rol]
        return None, None, f"El rol seleccionado solo permite {nombre_area}"

    return id_rol, area_esperada, None


#Usuarios
def _describir_usuario(id_rol, id_area, nombres, email, estado):
    """Texto de los datos de un usuario para AUDITORIA (RF30).

    Nunca incluye la contraseña ni su hash.
    """
    return (
        f"nombres={nombres}, email={email}, id_rol={id_rol}, "
        f"id_area={id_area}, estado={estado}"
    )


def _leer_usuario(cursor, id_usuario):
    """Datos actuales del usuario como tupla (id_rol, id_area, nombres, email, estado), o None."""
    cursor.execute(
        "SELECT id_rol, id_area, nombres, email, estado FROM usuario WHERE id_usuario = %s",
        (id_usuario,),
    )
    fila = cursor.fetchone()
    return tuple(fila) if fila else None


@usuarios_bp.route("/usuarios", methods=['POST'])
@roles_required(ROL_ADMINISTRADOR)
def create_usuario():
    connection = None
    cursor = None
    data = request.get_json()

    id_rol = data.get("id_rol")
    id_area = data.get("id_area")
    nombres = data.get("nombres")
    email = data.get("email")
    password = data.get("password")

    if not id_rol or not id_area or not nombres or not email or not password:
        return jsonify({"error": "Todos los campos son obligatorios"}), 400

    id_rol, id_area, error = resolver_area_para_rol(id_rol, id_area)

    if error:
        return jsonify({"error": error}), 422
    
    password_hash = hash_password(password)

    try:
        connection = get_connection()
        cursor = connection.cursor()

        sql = """INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash)
                 VALUES (%s, %s, %s, %s, %s)"""
        
        values = (id_rol, id_area, nombres, email, password_hash)

        cursor.execute(sql, values)
        id_nuevo = cursor.lastrowid

        registrar_auditoria(
            cursor, obtener_usuario_actual()["id_usuario"], "usuario", "USUARIO_CREADO",
            id_registro=id_nuevo,
            datos_nuevos=_describir_usuario(id_rol, id_area, nombres, email, "ACTIVO"),
        )
        connection.commit()

        return jsonify({"message": "Usuario registrado correctamente"}), 201
    
    except IntegrityError as error:
        if connection:
            connection.rollback()
        if error.errno == 1062:
            return jsonify({"error": "Ya existe un registro con esos datos únicos"}), 400
        if error.errno == 1452:
            return jsonify({"error": "Un rol o área indicada no existe"}), 422
        logger.exception("Error de integridad al guardar datos")
        return jsonify({"error": "Error interno al guardar datos"}), 500

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al registrar usuario")
        return jsonify({"error": "Error interno al registrar usuario"}), 500
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()



#Lista de usuarios
@usuarios_bp.route("/usuarios", methods=["GET"])
@login_required
def listar_usuarios():
    connection = None
    cursor = None

    try:
        id_rol = request.args.get("id_rol", type=int)
        id_area = request.args.get("id_area", type=int)
        estado = (request.args.get("estado") or "").strip().upper()
        ordenar_por = (request.args.get("ordenar_por") or "").strip().lower()
        direccion = (request.args.get("direccion") or "").strip().upper()

        if request.args.get("id_rol") and id_rol is None:
            return jsonify({"error": "El rol seleccionado no es válido"}), 400
        if request.args.get("id_area") and id_area is None:
            return jsonify({"error": "El área seleccionada no es válida"}), 400
        if id_rol is not None and id_rol <= 0:
            return jsonify({"error": "El rol seleccionado no es válido"}), 400
        if id_area is not None and id_area <= 0:
            return jsonify({"error": "El área seleccionada no es válida"}), 400
        if estado and estado not in ("ACTIVO", "INACTIVO"):
            return jsonify({"error": "El estado seleccionado no es válido"}), 400

        columnas_orden = {
            "nombre": "u.nombres",
            "fecha_registro": "u.fecha_creacion",
        }
        if ordenar_por and ordenar_por not in columnas_orden:
            return jsonify({"error": "El criterio de ordenamiento no es válido"}), 400
        if direccion and direccion not in ("ASC", "DESC"):
            return jsonify({"error": "La dirección de ordenamiento no es válida"}), 400

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
            LEFT JOIN area a ON u.id_area = a.id_area
        """
        filtros = []
        parametros = []
        if id_rol is not None:
            filtros.append("u.id_rol = %s")
            parametros.append(id_rol)
        if id_area is not None:
            filtros.append("u.id_area = %s")
            parametros.append(id_area)
        if estado:
            filtros.append("u.estado = %s")
            parametros.append(estado)
        if filtros:
            sql += " WHERE " + " AND ".join(filtros)

        if ordenar_por:
            columna = columnas_orden[ordenar_por]
            direccion_sql = direccion or ("ASC" if ordenar_por == "nombre" else "DESC")
            sql += f" ORDER BY {columna} {direccion_sql}, u.id_usuario DESC"
        else:
            sql += " ORDER BY u.id_usuario DESC"

        cursor.execute(sql, tuple(parametros))
        usuarios = cursor.fetchall()

        return jsonify(usuarios), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al listar usuarios")
        return jsonify({"error": "Error interno al listar usuarios"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

#Obtener usuario
@usuarios_bp.route("/usuarios/<int:id_usuario>", methods=["GET"])
@roles_required(ROL_ADMINISTRADOR)
def obtener_usuario(id_usuario):
    connection = None
    cursor = None

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

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al obtener usuario")
        return jsonify({"error": "Error interno al obtener usuario"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

#Actualizar usuario
@usuarios_bp.route("/usuarios/<int:id_usuario>", methods=["PUT"])
@roles_required(ROL_ADMINISTRADOR)
def actualizar_usuario(id_usuario):
    connection = None
    cursor = None
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

    if estado not in ("ACTIVO", "INACTIVO"):
        return jsonify({"error": "Estado no válido"}), 400

    id_rol, id_area, error = resolver_area_para_rol(id_rol, id_area)

    if error:
        return jsonify({"error": error}), 422

    try:
        connection = get_connection()
        cursor = connection.cursor()

        anterior = _leer_usuario(cursor, id_usuario)

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

        if cursor.rowcount == 0 and anterior is None:
            connection.rollback()
            return jsonify({"error": "Usuario no encontrado"}), 404

        # RF30 — solo se audita un cambio efectivo, con el antes y el después.
        nuevo = (id_rol, id_area, nombres, email, estado)
        if anterior != nuevo:
            registrar_auditoria(
                cursor, obtener_usuario_actual()["id_usuario"], "usuario", "USUARIO_MODIFICADO",
                id_registro=id_usuario,
                datos_anteriores=_describir_usuario(*anterior) if anterior else None,
                datos_nuevos=_describir_usuario(*nuevo),
            )
        connection.commit()

        return jsonify({
            "message": "Usuario actualizado correctamente"
        }), 200

    except IntegrityError as error:
        if connection:
            connection.rollback()
        if error.errno == 1062:
            return jsonify({"error": "Ya existe un registro con esos datos únicos"}), 400
        if error.errno == 1452:
            return jsonify({"error": "Un rol o área indicada no existe"}), 422
        logger.exception("Error de integridad al guardar datos")
        return jsonify({"error": "Error interno al guardar datos"}), 500

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al actualizar usuario")
        return jsonify({
            "error": "Error interno al actualizar usuario"
        }), 500

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()



#Desactivar usuario
@usuarios_bp.route("/usuarios/<int:id_usuario>/desactivar", methods=["PUT"])
@roles_required(ROL_ADMINISTRADOR)
def desactivar_usuario(id_usuario):
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        anterior = _leer_usuario(cursor, id_usuario)

        sql = """
            UPDATE usuario
            SET estado = 'INACTIVO'
            WHERE id_usuario = %s
        """

        cursor.execute(sql, (id_usuario,))

        if cursor.rowcount == 0 and anterior is None:
            connection.rollback()
            return jsonify({"error": "Usuario no encontrado"}), 404

        # RF30 — si ya estaba inactivo no hubo cambio que registrar.
        if anterior is None or anterior[4] != "INACTIVO":
            registrar_auditoria(
                cursor, obtener_usuario_actual()["id_usuario"], "usuario", "USUARIO_DESACTIVADO",
                id_registro=id_usuario,
                datos_anteriores=f"estado={anterior[4]}" if anterior else None,
                datos_nuevos="estado=INACTIVO",
            )
        connection.commit()

        return jsonify({
            "message": "Usuario deshabilitado correctamente"
        }), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al desactivar usuario")
        return jsonify({"error": "Error interno al desactivar usuario"}), 500

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


#Asignar rol a usuario
@usuarios_bp.route("/usuarios/<int:id_usuario>/rol", methods=["PUT"])
@roles_required(ROL_ADMINISTRADOR)
def asignar_rol_usuario(id_usuario):
    connection = None
    cursor = None
    data = request.get_json()

    id_rol = data.get("id_rol")

    if not id_rol:
        return jsonify({"error": "Debe seleccionar un rol"}), 400

    id_rol, id_area, error = resolver_area_para_rol(
        id_rol,
        validar_area=False,
    )

    if error:
        return jsonify({"error": error}), 422

    try:
        connection = get_connection()
        cursor = connection.cursor()

        anterior = _leer_usuario(cursor, id_usuario)

        sql = """
            UPDATE usuario
            SET id_rol = %s,
                id_area = %s
            WHERE id_usuario = %s
        """

        cursor.execute(sql, (id_rol, id_area, id_usuario))

        if cursor.rowcount == 0 and anterior is None:
            connection.rollback()
            return jsonify({"error": "Usuario no encontrado"}), 404

        # RF30 — solo se audita un cambio efectivo de rol.
        if anterior is None or (anterior[0], anterior[1]) != (id_rol, id_area):
            registrar_auditoria(
                cursor, obtener_usuario_actual()["id_usuario"], "usuario", "ROL_USUARIO_MODIFICADO",
                id_registro=id_usuario,
                datos_anteriores=f"id_rol={anterior[0]}, id_area={anterior[1]}" if anterior else None,
                datos_nuevos=f"id_rol={id_rol}, id_area={id_area}",
            )
        connection.commit()

        return jsonify({
            "message": "Rol asignado correctamente"
        }), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al asignar rol")
        return jsonify({"error": "Error interno al asignar rol"}), 500

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()
