import logging
from datetime import datetime

from mysql.connector import IntegrityError
from mysql.connector.errors import DatabaseError

from flask import Blueprint, request, jsonify
from backend.config.db import get_connection
from backend.utils.auditoria import registrar_auditoria
from backend.utils.auth import ROL_ADMINISTRADOR, login_required, obtener_usuario_actual, roles_required
from backend.utils.security import (
    LARGO_MINIMO_PASSWORD,
    error_de_password_nueva,
    generar_password_temporal,
    hash_password,
)

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

FORMATO_FECHA_HORA = "%Y-%m-%d %H:%M:%S"


def _con_fecha_en_texto(usuario):
    """Flask serializa un datetime como «Thu, 05 Nov 2026 00:57:12 GMT»: en inglés y con una
    zona que MySQL no guardó. La fecha de registro sale con el mismo formato del historial."""
    fecha = usuario.get("fecha_creacion")
    if isinstance(fecha, datetime):
        usuario["fecha_creacion"] = fecha.strftime(FORMATO_FECHA_HORA)
    return usuario


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


# SEC-03 — el sistema debe conservar siempre al menos un administrador activo.
MENSAJE_ULTIMO_ADMINISTRADOR = (
    "No se puede realizar esta operación porque el sistema debe conservar "
    "al menos un administrador activo."
)
MENSAJE_CONFLICTO_CONCURRENCIA = (
    "La operación entró en conflicto con otra operación simultánea. "
    "Intente nuevamente."
)
# Errores de MySQL que indican competencia por bloqueos, no un fallo de datos.
ERRNO_LOCK_WAIT_TIMEOUT = 1205
ERRNO_DEADLOCK = 1213


def _conserva_un_administrador_activo(cursor, id_usuario, seguira_siendo_administrador_activo):
    """Comprueba que la operación no deje al sistema sin administradores activos.

    Debe llamarse como PRIMERA sentencia de la transacción, antes de leer o
    modificar el usuario objetivo, y la transacción debe confirmarse o
    revertirse después.

    Estrategia (InnoDB):
    - `SELECT ... FOR UPDATE` bloquea a todos los administradores activos, en
      orden ascendente de id. Todas las operaciones que pueden reducir ese
      conjunto bloquean en el mismo orden, así que dos solicitudes simultáneas
      se serializan y no se produce un interbloqueo entre ellas.
    - Una lectura con bloqueo siempre lee la versión confirmada más reciente
      (no la instantánea de REPEATABLE READ): la segunda solicitud, al
      obtener el bloqueo, ve el efecto ya confirmado de la primera.
    - Al hacerlo antes de cualquier lectura sin bloqueo, la instantánea de la
      transacción se crea después de tomar los bloqueos.

    `seguira_siendo_administrador_activo` indica si, una vez aplicada la
    operación, el usuario objetivo seguirá siendo ADMINISTRADOR y ACTIVO.

    Devuelve True si la operación puede continuar.
    """
    cursor.execute(
        "SELECT id_usuario FROM usuario "
        "WHERE id_rol = %s AND estado = 'ACTIVO' "
        "ORDER BY id_usuario FOR UPDATE",
        (ROL_ID_ADMINISTRADOR,),
    )
    activos = {fila["id_usuario"] if isinstance(fila, dict) else fila[0] for fila in cursor.fetchall()}

    if id_usuario not in activos:
        # El objetivo no es hoy un administrador activo: la operación no puede
        # reducir el conjunto de administradores activos.
        return True

    return seguira_siendo_administrador_activo or len(activos) > 1


def _es_error_de_concurrencia(error):
    return isinstance(error, DatabaseError) and getattr(error, "errno", None) in (
        ERRNO_LOCK_WAIT_TIMEOUT,
        ERRNO_DEADLOCK,
    )


def _respuesta_conflicto_concurrencia(error):
    logger.warning("Conflicto de concurrencia al administrar usuarios (errno %s)", error.errno)
    return jsonify({"error": MENSAJE_CONFLICTO_CONCURRENCIA}), 409


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

    if not id_rol or not id_area or not nombres or not email:
        return jsonify({"error": "Todos los campos son obligatorios"}), 400

    # La contraseña inicial es SIEMPRE temporal: la persona debe cambiarla en su primer acceso. Lo habitual
    # es no enviar `password` y que el servidor genere una aleatoria; se acepta una indicada por el
    # administrador solo por compatibilidad (con la misma política y la misma obligación de cambio).
    generada = not password
    if generada:
        password = generar_password_temporal()
    else:
        error_politica = error_de_password_nueva(password)
        if error_politica:
            return jsonify({"error": error_politica}), 400

    id_rol, id_area, error = resolver_area_para_rol(id_rol, id_area)

    if error:
        return jsonify({"error": error}), 422
    
    password_hash = hash_password(password)

    try:
        connection = get_connection()
        cursor = connection.cursor()

        sql = """INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, debe_cambiar_password)
                 VALUES (%s, %s, %s, %s, %s, TRUE)"""
        
        values = (id_rol, id_area, nombres, email, password_hash)

        cursor.execute(sql, values)
        id_nuevo = cursor.lastrowid

        registrar_auditoria(
            cursor, obtener_usuario_actual()["id_usuario"], "usuario", "USUARIO_CREADO",
            id_registro=id_nuevo,
            datos_nuevos=_describir_usuario(id_rol, id_area, nombres, email, "ACTIVO")
            + " | contraseña temporal con cambio obligatorio",
        )
        connection.commit()

        respuesta = {
            "message": "Usuario registrado correctamente",
            "debe_cambiar_password": True,
        }
        if generada:
            # Se entrega UNA sola vez, en esta respuesta; nunca se guarda en claro ni se puede consultar después.
            respuesta["password_temporal"] = password
        resultado = jsonify(respuesta)
        resultado.headers["Cache-Control"] = "no-store"
        return resultado, 201
    
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



# Lista de usuarios (RF25).
#
# El administrador recibe la lista completa. Los usuarios operativos la necesitan
# para elegir responsables al crear o editar tareas, pero no para ver correos,
# roles ni fechas de alta: reciben solo las personas activas, con su nombre y
# área. Con esa respuesta limitada tampoco pueden usar el filtro por rol ni el
# orden por fecha de registro para deducir datos que no se les muestran.
@usuarios_bp.route("/usuarios", methods=["GET"])
@login_required
def listar_usuarios():
    connection = None
    cursor = None
    es_administrador = obtener_usuario_actual()["nombre_rol"] == ROL_ADMINISTRADOR

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

        if not es_administrador:
            if request.args.get("id_rol"):
                return jsonify({"error": "No tiene permisos para filtrar usuarios por rol"}), 403
            if estado == "INACTIVO":
                return jsonify([]), 200
            ordenar_por = direccion = ""

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

        if es_administrador:
            sql = """
                SELECT
                    u.id_usuario,
                    u.id_rol,
                    u.id_area,
                    u.nombres,
                    u.email,
                    u.estado,
                    u.fecha_creacion,
                    u.debe_cambiar_password,
                    r.nombre_rol,
                    a.nombre_area
                FROM usuario u
                INNER JOIN rol r ON u.id_rol = r.id_rol
                LEFT JOIN area a ON u.id_area = a.id_area
            """
        else:
            sql = """
                SELECT u.id_usuario, u.nombres, u.id_area, a.nombre_area, u.estado
                FROM usuario u
                LEFT JOIN area a ON u.id_area = a.id_area
            """
            estado = "ACTIVO"
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
        elif es_administrador:
            sql += " ORDER BY u.id_usuario DESC"
        else:
            sql += " ORDER BY u.nombres ASC, u.id_usuario ASC"

        cursor.execute(sql, tuple(parametros))
        usuarios = [_con_fecha_en_texto(usuario) for usuario in cursor.fetchall()]
        for usuario in usuarios:
            if "debe_cambiar_password" in usuario:
                usuario["debe_cambiar_password"] = bool(usuario["debe_cambiar_password"])

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

        return jsonify(_con_fecha_en_texto(usuario)), 200

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

        # SEC-03: primera sentencia de la transacción (ver la función).
        if not _conserva_un_administrador_activo(
            cursor, id_usuario, id_rol == ROL_ID_ADMINISTRADOR and estado == "ACTIVO"
        ):
            connection.rollback()
            return jsonify({"error": MENSAJE_ULTIMO_ADMINISTRADOR}), 409

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

    except Exception as error:
        if connection:
            connection.rollback()
        if _es_error_de_concurrencia(error):
            return _respuesta_conflicto_concurrencia(error)
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

        # SEC-03: primera sentencia de la transacción (ver la función).
        if not _conserva_un_administrador_activo(cursor, id_usuario, False):
            connection.rollback()
            return jsonify({"error": MENSAJE_ULTIMO_ADMINISTRADOR}), 409

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

    except Exception as error:
        if connection:
            connection.rollback()
        if _es_error_de_concurrencia(error):
            return _respuesta_conflicto_concurrencia(error)
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

        # SEC-03: primera sentencia de la transacción (ver la función). Un
        # administrador activo conserva su estado ACTIVO al cambiar de rol.
        if not _conserva_un_administrador_activo(
            cursor, id_usuario, id_rol == ROL_ID_ADMINISTRADOR
        ):
            connection.rollback()
            return jsonify({"error": MENSAJE_ULTIMO_ADMINISTRADOR}), 409

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

    except Exception as error:
        if connection:
            connection.rollback()
        if _es_error_de_concurrencia(error):
            return _respuesta_conflicto_concurrencia(error)
        logger.exception("Error al asignar rol")
        return jsonify({"error": "Error interno al asignar rol"}), 500

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


# Restablecimiento administrativo de contraseña.
#
# Genera una contraseña temporal nueva, invalida la anterior y las sesiones abiertas del usuario (sube su
# versión de credenciales), anula los enlaces de recuperación que siguieran vigentes y lo obliga a
# establecer una contraseña propia en su próximo acceso. La temporal se devuelve UNA sola vez. El
# administrador no puede usarlo sobre su propia cuenta: para esa cuenta existe el cambio personal
# (/auth/cambiar-password), que además evita bloquear por accidente el único acceso administrativo.
@usuarios_bp.route("/usuarios/<int:id_usuario>/restablecer-password", methods=["POST"])
@roles_required(ROL_ADMINISTRADOR)
def restablecer_password_usuario(id_usuario):
    datos = request.get_json(silent=True) or {}
    if datos.get("confirmar") is not True:
        return jsonify({"error": "Debe confirmar el restablecimiento de la contraseña"}), 400

    id_admin = obtener_usuario_actual()["id_usuario"]
    if id_usuario == id_admin:
        return jsonify({
            "error": "Para su propia cuenta use el cambio de contraseña personal."
        }), 409

    connection = None
    cursor = None
    try:
        connection = get_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_usuario, estado FROM usuario WHERE id_usuario = %s FOR UPDATE",
            (id_usuario,),
        )
        usuario = cursor.fetchone()
        if not usuario:
            connection.rollback()
            return jsonify({"error": "El usuario no existe"}), 404

        temporal = generar_password_temporal()
        cursor.execute(
            "UPDATE usuario SET password_hash = %s, debe_cambiar_password = TRUE, "
            "version_credenciales = version_credenciales + 1 WHERE id_usuario = %s",
            (hash_password(temporal), id_usuario),
        )
        # Ningún enlace de recuperación anterior puede reabrir credenciales previas.
        cursor.execute(
            "UPDATE token_recuperacion SET utilizado = TRUE WHERE id_usuario = %s AND utilizado = FALSE",
            (id_usuario,),
        )
        registrar_auditoria(
            cursor, id_admin, "usuario", "CONTRASENA_TEMPORAL_RESTABLECIDA",
            id_registro=id_usuario,
            datos_nuevos="restablecimiento administrativo; cambio obligatorio en el próximo acceso; "
                         "contraseña y sesiones anteriores invalidadas",
        )
        connection.commit()

        respuesta = jsonify({
            "message": "Contraseña restablecida. Entregue la contraseña temporal a la persona: no se volverá a mostrar.",
            "password_temporal": temporal,
            "debe_cambiar_password": True,
        })
        respuesta.headers["Cache-Control"] = "no-store"
        return respuesta, 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al restablecer la contraseña de un usuario")
        return jsonify({"error": "Error interno al restablecer la contraseña"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
