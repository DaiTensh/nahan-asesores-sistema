import hashlib
import logging
import os
import secrets

from flask import Blueprint, request, jsonify, session
from backend.config.db import get_connection
from backend.routes.notificaciones_routes import IMPORTANCIA_CRITICA, crear_notificacion
from backend.utils.auditoria import registrar_auditoria
from backend.utils.auth import (
    AVISO_SEGUNDOS_RANGO,
    INACTIVIDAD_MINUTOS_RANGO,
    PARAMETRO_AVISO,
    PARAMETRO_INACTIVIDAD,
    ROL_ADMINISTRADOR,
    abrir_sesion,
    invalidar_cache_config_sesion,
    login_required,
    marcar_actividad,
    obtener_config_sesion,
    obtener_usuario_actual,
    permite_cambio_pendiente,
    roles_required,
    segundos_restantes_sesion,
)
from backend.utils.clientes_recientes import (
    CLIENTES_RECIENTES_DEFECTO,
    PARAMETRO_CLIENTES_RECIENTES,
    validar_limite_clientes_recientes,
)
from backend.utils.correo import cuerpo_restablecimiento, enviar_correo
from backend.utils.limitador_login import (
    LimiteAlcanzado,
    LimitadorNoDisponible,
    calcular_clave_cuenta,
    liberar_reserva,
    normalizar_ip,
    purgar_si_corresponde,
    reservar_intento,
    respuesta_limite,
    respuesta_no_disponible,
    verificar_cupo,
)
from backend.utils.security import (
    LARGO_MINIMO_PASSWORD,
    check_password,
    error_de_password_nueva,
    hash_password,
)

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

_HASH_SENUELO = None


def _hash_senuelo():
    """Hash bcrypt con el mismo costo que los reales, calculado una vez; nunca coincide con una contraseña real."""
    global _HASH_SENUELO
    if _HASH_SENUELO is None:
        _HASH_SENUELO = hash_password(secrets.token_urlsafe(24))
    return _HASH_SENUELO


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
                a.nombre_area,
                u.debe_cambiar_password,
                u.version_credenciales
            FROM usuario u
            INNER JOIN rol r ON u.id_rol = r.id_rol
            INNER JOIN area a ON u.id_area = a.id_area
            WHERE u.email = %s
        """

        cursor.execute(sql, (email,))
        usuario = cursor.fetchone()

        # SEC-02 — límite de intentos fallidos (backend/utils/limitador_login.py).
        # Cada intento reserva cupo antes de comprobar la contraseña; la
        # reserva se conserva si el intento falla y se borra si tiene éxito.
        # No se mantiene ningún bloqueo ni transacción durante bcrypt.
        ip_cliente = normalizar_ip(request.remote_addr)
        if ip_cliente is None:
            logger.warning(
                "Login: IP de cliente no disponible o de loopback; se omiten los límites "
                "por IP y por cuenta+IP (¿TRUST_PROXY?)"
            )
        clave_cuenta = calcular_clave_cuenta(cursor, email)
        verificar_cupo(cursor, clave_cuenta, ip_cliente)
        id_reserva = reservar_intento(
            connection, cursor, clave_cuenta, ip_cliente,
            usuario["id_usuario"] if usuario else None,
        )
        purgar_si_corresponde(connection, cursor, id_reserva)

        if not usuario:
            # Con un correo inexistente no había bcrypt: respondía en ~6 ms contra ~240 ms de una cuenta real,
            # y esa diferencia delataba qué correos existen. Se gasta el mismo tiempo con un hash señuelo.
            check_password(password, _hash_senuelo())
            return jsonify({
                "error": "Credenciales incorrectas"
            }), 401

        # La contraseña se comprueba antes que el estado: quien no la conoce recibe el mismo mensaje
        # que para un correo inexistente y no puede averiguar qué cuentas existen o están inactivas.
        password_valida = check_password(password, usuario["password_hash"])

        if not password_valida:
            return jsonify({
                "error": "Credenciales incorrectas"
            }), 401

        if usuario["estado"] != "ACTIVO":
            return jsonify({
                "error": "Usuario inactivo. Contacte al administrador."
            }), 403

        # RF30 — el inicio de sesión queda en AUDITORIA antes de abrir la
        # sesión: si no se puede registrar, no se inicia. Los intentos
        # fallidos no se registran (no hay un usuario identificado).
        # SEC-02: un login exitoso no es un intento fallido; su reserva se
        # borra en la misma transacción que el LOGIN.
        liberar_reserva(cursor, id_reserva)
        registrar_auditoria(
            cursor, usuario["id_usuario"], "sesion", "LOGIN",
            id_registro=usuario["id_usuario"],
        )
        connection.commit()

        abrir_sesion(
            usuario["id_usuario"], usuario["id_rol"], usuario["id_area"], usuario["nombres"],
            usuario.get("version_credenciales"),
        )

        usuario.pop("password_hash")
        usuario.pop("version_credenciales", None)
        usuario["debe_cambiar_password"] = bool(usuario.get("debe_cambiar_password"))

        return jsonify({
            "message": "Inicio de sesión correcto",
            "usuario": usuario
        }), 200

    except LimiteAlcanzado as limite:
        return respuesta_limite(limite.segundos)

    except LimitadorNoDisponible as error:
        return respuesta_no_disponible(error.segundos)

    except Exception:
        logger.exception("Error al iniciar sesión")
        # SEC-02: si el login no se completa, se deshace el borrado de la
        # reserva y el intento sigue contando como fallido.
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                logger.warning("Login: no se pudo revertir la transacción")
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
@permite_cambio_pendiente
def auth_me():
    actual = obtener_usuario_actual()
    # El objeto `usuario` conserva su contrato; el estado del cambio obligatorio va aparte, en el nivel
    # superior, y lo decide el servidor (no el navegador).
    usuario = {clave: valor for clave, valor in actual.items() if clave != "debe_cambiar_password"}

    return jsonify({
        "usuario": usuario,
        "permisos": {
            "es_admin": usuario["nombre_rol"] == "ADMINISTRADOR"
        },
        "debe_cambiar_password": bool(actual.get("debe_cambiar_password")),
    }), 200


def _registrar_cierre_de_sesion():
    """RF30 — deja el LOGOUT en AUDITORIA mientras la sesión sigue vigente.

    Sin sesión no hay actor, así que no se registra nada. Un fallo al
    registrar no impide cerrar la sesión: salir siempre debe funcionar.
    """
    usuario = obtener_usuario_actual()
    if not usuario:
        return

    connection = None
    cursor = None
    try:
        connection = get_connection()
        if connection is None:
            return
        cursor = connection.cursor()
        registrar_auditoria(
            cursor, usuario["id_usuario"], "sesion", "LOGOUT",
            id_registro=usuario["id_usuario"],
        )
        connection.commit()
    except Exception:
        if connection:
            connection.rollback()
        logger.exception("No se pudo registrar el cierre de sesión")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@auth_bp.route("/logout", methods=["POST"])
def logout():
    _registrar_cierre_de_sesion()
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
@permite_cambio_pendiente
def estado_sesion():
    """Tiempo restante de la sesión. El frontend la consulta periódicamente
    con la cabecera `X-Actividad: pasiva`, así la consulta no renueva el plazo."""
    return jsonify(_estado_sesion()), 200


@auth_bp.route("/auth/sesion/extender", methods=["POST"])
@login_required
@permite_cambio_pendiente
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


@auth_bp.route("/parametros/clientes-recientes", methods=["GET"])
@roles_required(ROL_ADMINISTRADOR)
def obtener_parametros_clientes_recientes():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "Error de conexión con la base de datos"}), 500
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT valor_parametro FROM parametros_sistema WHERE nombre_parametro = %s",
            (PARAMETRO_CLIENTES_RECIENTES,),
        )
        fila = cursor.fetchone()
        limite = validar_limite_clientes_recientes(
            fila.get("valor_parametro") if fila else None
        ) or CLIENTES_RECIENTES_DEFECTO
        return jsonify({"limite": limite}), 200
    except Exception:
        logger.exception("Error al leer la configuración de clientes recientes")
        return jsonify({"error": "No se pudo leer la configuración."}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@auth_bp.route("/parametros/clientes-recientes", methods=["PUT"])
@roles_required(ROL_ADMINISTRADOR)
def actualizar_parametros_clientes_recientes():
    data = request.get_json(silent=True)
    limite = validar_limite_clientes_recientes(
        data.get("limite") if isinstance(data, dict) else None
    )
    if limite is None:
        return jsonify({"error": "El límite debe ser un entero entre 1 y 20."}), 400

    usuario = obtener_usuario_actual()
    connection = None
    cursor = None
    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "Error de conexión con la base de datos"}), 500
        cursor = connection.cursor(dictionary=True)
        valor_anterior = _guardar_parametro(
            cursor,
            PARAMETRO_CLIENTES_RECIENTES,
            limite,
            "Máximo global de clientes recientes mostrados por usuario",
        )
        registrar_auditoria(
            cursor,
            usuario["id_usuario"],
            "parametros_sistema",
            "CONFIGURAR_CLIENTES_RECIENTES",
            datos_anteriores=f"{PARAMETRO_CLIENTES_RECIENTES}={valor_anterior}",
            datos_nuevos=f"{PARAMETRO_CLIENTES_RECIENTES}={limite}",
        )
        connection.commit()
        return jsonify({"message": "Configuración actualizada", "limite": limite}), 200
    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al actualizar la configuración de clientes recientes")
        return jsonify({"error": "No se pudo guardar la configuración."}), 500
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

    # RF46 — una solicitud de seguridad es crítica para quien administra.
    for administrador in administradores:
        crear_notificacion(
            cursor, administrador["id_usuario"], "SEGURIDAD", mensaje,
            "/frontend/usuarios/usuarios.html",
            importancia=IMPORTANCIA_CRITICA,
        )


# SEC-04 — límite de solicitudes efectivas (las que generan un token) por cuenta.
#
# Se cuenta sobre token_recuperacion, que ya guarda una fila por solicitud
# efectiva y su fecha de emisión, así que no hace falta otro almacén y el
# límite vale para todos los workers de Gunicorn y sobrevive a reinicios.
#
# Contar y luego insertar no basta: dos solicitudes simultáneas para la misma
# cuenta leerían el mismo conteo y ambas pasarían. Por eso las solicitudes de
# una misma cuenta se serializan con un bloqueo con nombre de MySQL
# (GET_LOCK), que es del servidor, no de un proceso. Se eligió frente a
# bloquear la fila de `usuario` con FOR UPDATE porque esa fila también la
# toman, en modo compartido, las claves foráneas de las notificaciones a los
# administradores: dos solicitudes sobre dos administradores distintos se
# habrían bloqueado entre sí (interbloqueo).
#
# Solo hay un bloqueo por solicitud y sin otros bloqueos de fila encima de
# él, de modo que no puede haber ciclos. Si no se obtiene en
# SEGUNDOS_ESPERA_BLOQUEO se responde como al superar el límite (falla
# cerrada).
MAX_SOLICITUDES_RECUPERACION = 3
VENTANA_SOLICITUDES_MINUTOS = 60
SEGUNDOS_ESPERA_BLOQUEO = 5


def _nombre_bloqueo_recuperacion(id_usuario):
    return f"nahan:recuperar:{id_usuario}"


def _adquirir_bloqueo_recuperacion(cursor, id_usuario):
    cursor.execute(
        "SELECT GET_LOCK(%s, %s) AS bloqueo",
        (_nombre_bloqueo_recuperacion(id_usuario), SEGUNDOS_ESPERA_BLOQUEO),
    )
    fila = cursor.fetchone()
    return bool(fila) and fila["bloqueo"] == 1


def _liberar_bloqueo_recuperacion(cursor, id_usuario):
    cursor.execute(
        "SELECT RELEASE_LOCK(%s) AS liberado",
        (_nombre_bloqueo_recuperacion(id_usuario),),
    )
    cursor.fetchone()


def _solicitudes_recientes(cursor, id_usuario):
    """Solicitudes efectivas de la cuenta dentro de la ventana móvil, según el
    reloj de la base (el mismo que escribe fecha_emision)."""
    cursor.execute(
        "SELECT COUNT(*) AS total FROM token_recuperacion "
        "WHERE id_usuario = %s AND fecha_emision > DATE_SUB(NOW(), INTERVAL %s MINUTE)",
        (id_usuario, VENTANA_SOLICITUDES_MINUTOS),
    )
    fila = cursor.fetchone()
    return int(fila["total"]) if fila else 0


@auth_bp.route("/auth/recuperar", methods=["POST"])
def solicitar_restablecimiento():
    connection = None
    cursor = None
    id_con_bloqueo = None
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
            # SEC-04: se serializan las solicitudes de la cuenta y se termina la
            # transacción de lectura para que el conteo de abajo parta de una
            # instantánea posterior a la última solicitud confirmada (el
            # bloqueo se libera solo después del commit).
            if not _adquirir_bloqueo_recuperacion(cursor, usuario["id_usuario"]):
                logger.warning("No se obtuvo el bloqueo de recuperación (usuario %s)", usuario["id_usuario"])
                return jsonify({"message": MENSAJE_SOLICITUD}), 200
            id_con_bloqueo = usuario["id_usuario"]
            connection.rollback()

            if _solicitudes_recientes(cursor, id_con_bloqueo) >= MAX_SOLICITUDES_RECUPERACION:
                # Misma respuesta que cualquier otra solicitud: sin token nuevo,
                # sin invalidar el vigente, sin aviso a administradores y sin
                # correo. Tampoco se usa 429 para no revelar que la cuenta existe.
                logger.info("Solicitud de restablecimiento omitida por límite (usuario %s)", id_con_bloqueo)
                return jsonify({"message": MENSAJE_SOLICITUD}), 200

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
            # Liberar antes del envío: el SMTP puede tardar hasta 15 s y no debe
            # retener a las demás solicitudes de la cuenta.
            _liberar_bloqueo_recuperacion(cursor, id_con_bloqueo)
            id_con_bloqueo = None

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
        if cursor and id_con_bloqueo is not None:
            # Caminos sin commit (límite, error): el cierre de la conexión también
            # lo libera, esto solo evita retenerlo hasta entonces.
            try:
                _liberar_bloqueo_recuperacion(cursor, id_con_bloqueo)
            except Exception:
                logger.warning("No se pudo liberar el bloqueo de recuperación (usuario %s)", id_con_bloqueo)

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

        # La contraseña la elige la propia persona: deja de haber cambio pendiente y sube la versión de
        # credenciales, de modo que cualquier contraseña temporal anterior y toda sesión abierta quedan sin efecto.
        cursor.execute(
            "UPDATE usuario SET password_hash = %s, debe_cambiar_password = FALSE, "
            "version_credenciales = version_credenciales + 1 WHERE id_usuario = %s",
            (hash_password(password), registro["id_usuario"])
        )
        # Cualquier otro enlace que siguiera vigente para ese usuario deja de servir.
        cursor.execute(
            "UPDATE token_recuperacion SET utilizado = TRUE "
            "WHERE id_usuario = %s AND utilizado = FALSE",
            (registro["id_usuario"],)
        )
        # RF30 — solo queda constancia de que ocurrió: ni la contraseña, ni
        # su hash, ni el token se guardan en AUDITORIA.
        registrar_auditoria(
            cursor, registro["id_usuario"], "usuario", "CONTRASENA_RESTABLECIDA",
            id_registro=registro["id_usuario"],
            datos_nuevos="restablecimiento mediante enlace de recuperación",
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


# ---------------------------------------------------------------------------
# Cambio de contraseña personal (obligatorio tras una contraseña temporal, o voluntario)
# ---------------------------------------------------------------------------
# Reutiliza el hash, la política de contraseñas, la auditoría y el limitador de intentos del inicio de
# sesión (la contraseña actual es un intento de adivinar, igual que un login). Es la única ruta, junto con
# /auth/me, la sesión y el cierre de sesión, que sirve mientras el cambio está pendiente.

@auth_bp.route("/auth/cambiar-password", methods=["POST"])
@login_required
@permite_cambio_pendiente
def cambiar_password():
    data = request.get_json(silent=True) or {}
    actual = data.get("password_actual")
    nueva = data.get("password_nueva")
    confirmacion = data.get("confirmacion")

    if not all(isinstance(valor, str) and valor for valor in (actual, nueva, confirmacion)):
        return jsonify({"error": "La contraseña actual, la nueva y su confirmación son obligatorias"}), 400
    error_politica = error_de_password_nueva(nueva)
    if error_politica:
        return jsonify({"error": error_politica}), 400
    if nueva != confirmacion:
        return jsonify({"error": "La confirmación no coincide con la contraseña nueva"}), 400
    if nueva == actual:
        return jsonify({"error": "La contraseña nueva no puede ser igual a la actual"}), 400

    id_usuario = obtener_usuario_actual()["id_usuario"]
    connection = None
    cursor = None
    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "Servicio no disponible temporalmente"}), 503
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_usuario, email, password_hash, id_rol, id_area, nombres, version_credenciales "
            "FROM usuario WHERE id_usuario = %s AND estado = 'ACTIVO'",
            (id_usuario,),
        )
        usuario = cursor.fetchone()
        if not usuario:
            return jsonify({"error": "No autenticado"}), 401

        # Mismo límite de intentos que el inicio de sesión (SEC-02): la reserva se hace antes de comprobar
        # la contraseña, no se mantiene ninguna transacción durante bcrypt y se conserva si el intento falla.
        ip_cliente = normalizar_ip(request.remote_addr)
        clave_cuenta = calcular_clave_cuenta(cursor, usuario["email"])
        verificar_cupo(cursor, clave_cuenta, ip_cliente)
        id_reserva = reservar_intento(connection, cursor, clave_cuenta, ip_cliente, usuario["id_usuario"])

        if not check_password(actual, usuario["password_hash"]):
            return jsonify({"error": "La contraseña actual no es correcta"}), 400

        # Escritura atómica: se vuelve a leer la fila con bloqueo y solo se cambia si sigue siendo la misma
        # credencial (dos cambios simultáneos con la misma temporal: solo gana uno).
        connection.start_transaction()
        cursor.execute(
            "SELECT password_hash, version_credenciales FROM usuario WHERE id_usuario = %s FOR UPDATE",
            (id_usuario,),
        )
        vigente = cursor.fetchone()
        if (not vigente or vigente["password_hash"] != usuario["password_hash"]
                or int(vigente["version_credenciales"] or 0) != int(usuario["version_credenciales"] or 0)):
            connection.rollback()
            return jsonify({"error": "Las credenciales cambiaron mientras tanto. Inicie sesión de nuevo."}), 409

        liberar_reserva(cursor, id_reserva)
        version = int(usuario["version_credenciales"] or 0) + 1
        cursor.execute(
            "UPDATE usuario SET password_hash = %s, debe_cambiar_password = FALSE, "
            "version_credenciales = %s WHERE id_usuario = %s",
            (hash_password(nueva), version, id_usuario),
        )
        # Solo queda constancia de que ocurrió: ni contraseñas, ni hashes.
        registrar_auditoria(
            cursor, id_usuario, "usuario", "CONTRASENA_CAMBIADA",
            id_registro=id_usuario,
            datos_nuevos="cambio de contraseña personal; sesiones y contraseña anteriores invalidadas",
        )
        connection.commit()

        # Sesión renovada: nueva sesión atada a la nueva versión (las anteriores dejan de valer).
        abrir_sesion(id_usuario, usuario["id_rol"], usuario["id_area"], usuario["nombres"], version)
        return jsonify({"message": "Tu contraseña fue actualizada.", "debe_cambiar_password": False}), 200

    except LimiteAlcanzado as limite:
        if connection:
            connection.rollback()
        return respuesta_limite(limite.segundos)

    except LimitadorNoDisponible as error:
        if connection:
            connection.rollback()
        return respuesta_no_disponible(error.segundos)

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al cambiar la contraseña")
        return jsonify({"error": "Error interno al cambiar la contraseña"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
