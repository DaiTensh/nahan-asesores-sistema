import hashlib
import logging
import os
import secrets

from flask import Blueprint, request, jsonify, session
from backend.config.db import get_connection
from backend.utils.auditoria import registrar_auditoria
from backend.utils.auth import (
    AVISO_SEGUNDOS_RANGO,
    INACTIVIDAD_MINUTOS_RANGO,
    PARAMETRO_AVISO,
    PARAMETRO_INACTIVIDAD,
    ROL_ADMINISTRADOR,
    invalidar_cache_config_sesion,
    login_required,
    marcar_actividad,
    obtener_config_sesion,
    obtener_usuario_actual,
    roles_required,
    segundos_restantes_sesion,
)
from backend.utils.correo import cuerpo_restablecimiento, enviar_correo
from backend.utils.security import check_password, hash_password

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
        marcar_actividad()

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


# ---------------------------------------------------------------------------
# RF59 — Cerrando Automático por Inactividad
# ---------------------------------------------------------------------------
# El control del plazo vive en backend/utils/auth.py (obtener_usuario_actual).
# Aquí están las rutas que usa el aviso del frontend y la configuración del
# tiempo máximo, que solo puede cambiar un administrador.


def _estado_sesion():
    minutos, aviso = obtener_config_sesion()
    return {
        "segundos_restantes": segundos_restantes_sesion(),
        "limite_minutos": minutos,
        "aviso_segundos": aviso,
    }


@auth_bp.route("/auth/sesion", methods=["GET"])
@login_required
def estado_sesion():
    """Tiempo restante de la sesión. El frontend la consulta periódicamente
    con la cabecera `X-Actividad: pasiva`, así la consulta no renueva el plazo."""
    return jsonify(_estado_sesion()), 200


@auth_bp.route("/auth/sesion/extender", methods=["POST"])
@login_required
def extender_sesion():
    marcar_actividad()
    return jsonify(_estado_sesion()), 200


@auth_bp.route("/parametros/sesion", methods=["GET"])
@login_required
def obtener_parametros_sesion():
    minutos, aviso = obtener_config_sesion()
    return jsonify({"limite_minutos": minutos, "aviso_segundos": aviso}), 200


def _entero_en_rango(valor, minimo, maximo):
    if isinstance(valor, bool):
        return None
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    if str(numero) != str(valor).strip():
        return None
    return numero if minimo <= numero <= maximo else None


def _guardar_parametro(cursor, nombre, valor, descripcion):
    cursor.execute(
        "SELECT valor_parametro FROM parametros_sistema WHERE nombre_parametro = %s",
        (nombre,),
    )
    fila = cursor.fetchone()
    if fila:
        cursor.execute(
            "UPDATE parametros_sistema SET valor_parametro = %s WHERE nombre_parametro = %s",
            (str(valor), nombre),
        )
        return fila["valor_parametro"]

    cursor.execute(
        """
        INSERT INTO parametros_sistema (nombre_parametro, valor_parametro, tipo_dato, descripcion)
        VALUES (%s, %s, 'INT', %s)
        """,
        (nombre, str(valor), descripcion),
    )
    return None


@auth_bp.route("/parametros/sesion", methods=["PUT"])
@roles_required(ROL_ADMINISTRADOR)
def actualizar_parametros_sesion():
    data = request.get_json(silent=True) or {}
    minutos = _entero_en_rango(data.get("limite_minutos"), *INACTIVIDAD_MINUTOS_RANGO)
    aviso = _entero_en_rango(data.get("aviso_segundos"), *AVISO_SEGUNDOS_RANGO)

    if minutos is None:
        return jsonify({
            "error": "El tiempo de inactividad debe ser un número entero entre "
                     f"{INACTIVIDAD_MINUTOS_RANGO[0]} y {INACTIVIDAD_MINUTOS_RANGO[1]} minutos."
        }), 400
    if aviso is None:
        return jsonify({
            "error": "La anticipación del aviso debe ser un número entero entre "
                     f"{AVISO_SEGUNDOS_RANGO[0]} y {AVISO_SEGUNDOS_RANGO[1]} segundos."
        }), 400
    if aviso >= minutos * 60:
        return jsonify({"error": "El aviso debe mostrarse antes de que termine el tiempo de inactividad."}), 400

    usuario = obtener_usuario_actual()
    connection = None
    cursor = None
    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "Error de conexión con la base de datos"}), 500

        cursor = connection.cursor(dictionary=True)
        minutos_antes = _guardar_parametro(
            cursor, PARAMETRO_INACTIVIDAD, minutos,
            "Minutos de inactividad antes de cerrar la sesión automáticamente",
        )
        aviso_antes = _guardar_parametro(
            cursor, PARAMETRO_AVISO, aviso,
            "Segundos de anticipación con que se avisa el cierre por inactividad",
        )
        registrar_auditoria(
            cursor, usuario["id_usuario"], "parametros_sistema", "CONFIGURAR_SESION",
            datos_anteriores=f"{PARAMETRO_INACTIVIDAD}={minutos_antes}, {PARAMETRO_AVISO}={aviso_antes}",
            datos_nuevos=f"{PARAMETRO_INACTIVIDAD}={minutos}, {PARAMETRO_AVISO}={aviso}",
        )
        connection.commit()
        invalidar_cache_config_sesion()

        return jsonify({
            "message": "Configuración de sesión actualizada",
            "limite_minutos": minutos,
            "aviso_segundos": aviso,
        }), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al actualizar la configuración de sesión")
        return jsonify({"error": "Error interno al guardar la configuración"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


# ---------------------------------------------------------------------------
# RF26 — Restableciendo Contraseñas
# ---------------------------------------------------------------------------
# El flujo tiene tres pasos: el usuario pide el enlace, el sistema lo verifica
# cuando abre la página, y finalmente define la contraseña nueva.
#
# Decisiones de seguridad, todas exigidas por los criterios de aceptación del
# requerimiento o derivadas de ellos:
#
# - La solicitud responde siempre lo mismo, exista o no la cuenta. De otro modo
#   el formulario se convierte en un verificador de correos registrados.
# - En la base se guarda el hash SHA-256 del token, nunca el token en claro.
# - Cada solicitud invalida los enlaces anteriores del mismo usuario, así no
#   quedan varios vigentes a la vez.
# - El token se marca como utilizado al consumirse y caduca por tiempo.

MINUTOS_VIGENCIA_POR_DEFECTO = 60
LARGO_MINIMO_PASSWORD = 8
MENSAJE_SOLICITUD = (
    "Si el correo corresponde a una cuenta activa, enviamos un enlace para "
    "restablecer la contraseña. Revisa tu bandeja de entrada."
)


def _minutos_vigencia():
    try:
        minutos = int(os.getenv("RESET_TOKEN_MINUTOS", MINUTOS_VIGENCIA_POR_DEFECTO))
    except (TypeError, ValueError):
        return MINUTOS_VIGENCIA_POR_DEFECTO

    return minutos if minutos > 0 else MINUTOS_VIGENCIA_POR_DEFECTO


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _enlace_restablecimiento(token):
    base = os.getenv("APP_URL_FRONTEND", "http://127.0.0.1:5500/frontend").rstrip("/")

    return f"{base}/auth/restablecer.html?token={token}"


def _avisar_a_administradores(cursor, usuario):
    """Deja constancia de la solicitud para los administradores.

    La tabla NOTIFICACION ya existe en el modelo desde el Incremento 1 y este
    es su primer uso efectivo desde la aplicación.
    """
    cursor.execute(
        """
        SELECT u.id_usuario
        FROM usuario u
        INNER JOIN rol r ON u.id_rol = r.id_rol
        WHERE r.nombre_rol = 'ADMINISTRADOR' AND u.estado = 'ACTIVO'
        """
    )
    administradores = cursor.fetchall()

    if not administradores:
        return

    mensaje = (
        f"Se solicitó un restablecimiento de contraseña para la cuenta "
        f"{usuario['email']} ({usuario['nombres']})."
    )

    cursor.executemany(
        """
        INSERT INTO notificacion (id_usuario, tipo, mensaje, url_destino, leida)
        VALUES (%s, 'SEGURIDAD', %s, '/frontend/usuarios/usuarios.html', FALSE)
        """,
        [(administrador["id_usuario"], mensaje) for administrador in administradores]
    )


@auth_bp.route("/auth/recuperar", methods=["POST"])
def solicitar_restablecimiento():
    connection = None
    cursor = None
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()

    if not email:
        return jsonify({"error": "El correo electrónico es obligatorio"}), 400

    try:
        connection = get_connection()

        if connection is None:
            logger.error("Sin conexión a la base de datos al solicitar un restablecimiento")
            return jsonify({"error": "Servicio no disponible temporalmente"}), 503

        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_usuario, nombres, email FROM usuario WHERE email = %s AND estado = 'ACTIVO'",
            (email,)
        )
        usuario = cursor.fetchone()

        # La respuesta es idéntica exista o no la cuenta. Solo cambia lo que
        # ocurre por dentro.
        if usuario:
            cursor.execute(
                "UPDATE token_recuperacion SET utilizado = TRUE "
                "WHERE id_usuario = %s AND utilizado = FALSE",
                (usuario["id_usuario"],)
            )

            token = secrets.token_urlsafe(32)
            minutos = _minutos_vigencia()

            # La vigencia se calcula con el reloj de la base, no con el de la
            # aplicación. El sistema corre con la zona horaria de Santiago y el
            # servidor MySQL puede estar en UTC: si se mezclaran los dos relojes,
            # los enlaces caducarían con horas de diferencia según dónde se
            # ejecute cada parte.
            cursor.execute(
                "INSERT INTO token_recuperacion (id_usuario, token_hash, fecha_expiracion) "
                "VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL %s MINUTE))",
                (usuario["id_usuario"], _hash_token(token), minutos)
            )

            _avisar_a_administradores(cursor, usuario)
            connection.commit()

            enviar_correo(
                usuario["email"],
                "Restablecimiento de contraseña — Nahan Asesores",
                cuerpo_restablecimiento(usuario["nombres"], _enlace_restablecimiento(token), minutos)
            )
        else:
            logger.info("Solicitud de restablecimiento para un correo sin cuenta activa")

        return jsonify({"message": MENSAJE_SOLICITUD}), 200

    except Exception:
        if connection:
            connection.rollback()

        logger.exception("Error al solicitar el restablecimiento de contraseña")
        return jsonify({"error": "Error interno al procesar la solicitud"}), 500

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


def _buscar_token_vigente(cursor, token):
    cursor.execute(
        """
        SELECT t.id_token, t.id_usuario, u.nombres, u.email
        FROM token_recuperacion t
        INNER JOIN usuario u ON t.id_usuario = u.id_usuario
        WHERE t.token_hash = %s
          AND t.utilizado = FALSE
          AND t.fecha_expiracion > NOW()
          AND u.estado = 'ACTIVO'
        """,
        (_hash_token(token),)
    )

    return cursor.fetchone()


@auth_bp.route("/auth/recuperar/verificar", methods=["POST"])
def verificar_token_restablecimiento():
    """Permite que la pantalla avise que el enlace caducó antes de pedir la
    contraseña nueva. No revela a quién pertenece el token."""
    connection = None
    cursor = None
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()

    if not token:
        return jsonify({"valido": False}), 200

    try:
        connection = get_connection()

        if connection is None:
            return jsonify({"error": "Servicio no disponible temporalmente"}), 503

        cursor = connection.cursor(dictionary=True)

        return jsonify({"valido": bool(_buscar_token_vigente(cursor, token))}), 200

    except Exception:
        logger.exception("Error al verificar el token de restablecimiento")
        return jsonify({"error": "Error interno al verificar el enlace"}), 500

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


@auth_bp.route("/auth/restablecer", methods=["POST"])
def confirmar_restablecimiento():
    connection = None
    cursor = None
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    password = data.get("password") or ""

    if not token or not password:
        return jsonify({"error": "El enlace y la contraseña nueva son obligatorios"}), 400

    if len(password) < LARGO_MINIMO_PASSWORD:
        return jsonify({
            "error": f"La contraseña debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres"
        }), 400

    try:
        connection = get_connection()

        if connection is None:
            logger.error("Sin conexión a la base de datos al confirmar un restablecimiento")
            return jsonify({"error": "Servicio no disponible temporalmente"}), 503

        cursor = connection.cursor(dictionary=True)
        registro = _buscar_token_vigente(cursor, token)

        if not registro:
            return jsonify({
                "error": "El enlace no es válido o ya caducó. Solicita uno nuevo."
            }), 400

        cursor.execute(
            "UPDATE token_recuperacion SET utilizado = TRUE, fecha_uso = NOW() "
            "WHERE id_token = %s AND utilizado = FALSE AND fecha_expiracion > NOW()",
            (registro["id_token"],)
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return jsonify({"error": "El enlace no es válido o ya caducó. Solicita uno nuevo."}), 400

        cursor.execute(
            "UPDATE usuario SET password_hash = %s WHERE id_usuario = %s",
            (hash_password(password), registro["id_usuario"])
        )
        # Cualquier otro enlace que siguiera vigente para ese usuario deja de servir.
        cursor.execute(
            "UPDATE token_recuperacion SET utilizado = TRUE "
            "WHERE id_usuario = %s AND utilizado = FALSE",
            (registro["id_usuario"],)
        )
        connection.commit()

        logger.info("Contraseña restablecida para el usuario %s", registro["id_usuario"])

        return jsonify({"message": "Tu contraseña fue actualizada. Ya puedes iniciar sesión."}), 200

    except Exception:
        if connection:
            connection.rollback()

        logger.exception("Error al confirmar el restablecimiento de contraseña")
        return jsonify({"error": "Error interno al actualizar la contraseña"}), 500

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()
