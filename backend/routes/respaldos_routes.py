"""RF60 — Respaldando históricamente la información.

API de administración de respaldos: historial, estado del almacenamiento,
respaldo manual, verificación y restauración. Todas las rutas son solo para
administradores y la autorización se hace aquí, en el backend. Los paquetes de
respaldo nunca se sirven por HTTP: contienen toda la información del sistema.

Los respaldos programados no pasan por esta API: los ejecuta el temporizador
de systemd (backend/respaldos_programados.py).
"""
import logging
import os

from flask import Blueprint, jsonify, request

from backend.config.db import get_connection
from backend.utils import respaldos as servicio
from backend.utils.auditoria import registrar_auditoria
from backend.utils.auth import ROL_ADMINISTRADOR, obtener_usuario_actual, roles_required
from backend.utils.security import check_password

respaldos_bp = Blueprint("respaldos", __name__)
logger = logging.getLogger(__name__)

LIMITES_LISTADO = (10, 20, 50, 100)
LIMITE_DEFECTO = 20
PROGRAMACION = "Diaria a las 02:00 (nahan-respaldo.timer de systemd)"

TABLA_AUDITADA = "respaldo"
ACCION_RESPALDO_MANUAL = "RESPALDO_MANUAL"
ACCION_RESPALDO_FALLIDO = "RESPALDO_MANUAL_FALLIDO"
ACCION_RESTAURACION = "RESTAURACION_RESPALDO"
ACCION_RESTAURACION_FALLIDA = "RESTAURACION_FALLIDA"


def _fecha(valor):
    return valor.strftime("%Y-%m-%d %H:%M:%S") if hasattr(valor, "strftime") else (str(valor) if valor else None)


def _serializar(fila, directorio=None):
    nombre = fila.get("nombre_archivo")
    disponible = bool(
        nombre and fila.get("archivo_eliminado_en") is None and directorio
        and servicio.PATRON_NOMBRE_PAQUETE.match(nombre)
        and os.path.isfile(os.path.join(directorio, nombre))
    )
    duracion = fila.get("duracion_segundos")
    return {
        "id_respaldo": fila["id_respaldo"],
        "operacion": fila["operacion"],
        "tipo": fila["tipo"],
        "estado": fila["estado"],
        "fecha_inicio": _fecha(fila.get("fecha_inicio")),
        "fecha_fin": _fecha(fila.get("fecha_fin")),
        "duracion_segundos": float(duracion) if duracion is not None else None,
        "usuario": fila.get("usuario"),
        "id_relacionado": fila.get("id_relacionado"),
        "nombre_archivo": nombre,
        "tamano_bytes": fila.get("tamano_bytes"),
        "sha256": fila.get("sha256"),
        "detalle": fila.get("detalle"),
        "mensaje_error": fila.get("mensaje_error"),
        "archivo_disponible": disponible,
    }


def _auditar(usuario, accion, id_registro, datos):
    """Deja constancia en AUDITORIA sin que un fallo aquí oculte el resultado de la operación.

    Tras una restauración la tabla `usuario` puede ser la del respaldo, y el
    administrador que la ejecutó podría no existir en ella: en ese caso queda
    solo el historial de la tabla `respaldo`.
    """
    connection = cursor = None
    try:
        connection = get_connection()
        if connection is None:
            return
        cursor = connection.cursor()
        registrar_auditoria(cursor, usuario["id_usuario"], TABLA_AUDITADA, accion,
                            id_registro=id_registro, datos_nuevos=datos)
        connection.commit()
    except Exception:
        if connection:
            connection.rollback()
        logger.warning("No se pudo registrar %s en AUDITORIA", accion, exc_info=True)
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def _error(error):
    cuerpo = {"error": error.mensaje, "codigo": error.codigo}
    if getattr(error, "id_respaldo", None) is not None:
        cuerpo["id_respaldo"] = error.id_respaldo
    if getattr(error, "recuperacion", None):
        cuerpo["recuperacion"] = error.recuperacion
    return jsonify(cuerpo), error.estado_http


def _leer_limite(args):
    texto = (args.get("limite") or "").strip()
    if not texto:
        return LIMITE_DEFECTO, None
    if not (texto.isascii() and texto.isdigit()) or int(texto) not in LIMITES_LISTADO:
        return None, f"El límite debe ser uno de: {', '.join(str(v) for v in LIMITES_LISTADO)}."
    return int(texto), None


def _clave_valida(id_usuario, clave):
    connection = cursor = None
    try:
        connection = get_connection()
        if connection is None:
            return False
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT password_hash FROM usuario WHERE id_usuario = %s", (id_usuario,))
        fila = cursor.fetchone()
        return bool(fila) and check_password(clave, fila["password_hash"])
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@respaldos_bp.route("/respaldos", methods=["GET"])
@roles_required(ROL_ADMINISTRADOR)
def listar_respaldos():
    limite, error = _leer_limite(request.args)
    if error:
        return jsonify({"error": error}), 400
    try:
        config = servicio.ConfigRespaldo()
        filas = servicio.RegistroMySQL().listar(limite)
        directorio = config.directorio or None
        return jsonify({
            "respaldos": [_serializar(fila, directorio) for fila in filas],
            "limite": limite,
        }), 200
    except servicio.ErrorRespaldo as error:
        return _error(error)
    except Exception:
        logger.exception("Error al listar los respaldos")
        return jsonify({"error": "Error interno al consultar el historial de respaldos"}), 500


@respaldos_bp.route("/respaldos/estado", methods=["GET"])
@roles_required(ROL_ADMINISTRADOR)
def estado_respaldos():
    try:
        estado = servicio.estado_del_sistema()
    except Exception:
        logger.exception("Error al consultar el estado de los respaldos")
        return jsonify({"error": "Error interno al consultar el estado de los respaldos"}), 500

    ultimo = estado["ultimo_exitoso"]
    return jsonify({
        "almacenamiento": estado["almacenamiento"],
        "restauracion_habilitada": estado["restauracion_habilitada"],
        "base_de_destino": estado["base_de_destino"],
        "retencion_maxima": estado["retencion_maxima"],
        "operacion_en_curso": estado["operacion_en_curso"],
        "programacion": PROGRAMACION,
        "ultimo_exitoso": {
            "id_respaldo": ultimo["id_respaldo"],
            "tipo": ultimo["tipo"],
            "fecha_fin": _fecha(ultimo["fecha_fin"]),
            "tamano_bytes": ultimo["tamano_bytes"],
        } if ultimo else None,
    }), 200


@respaldos_bp.route("/respaldos", methods=["POST"])
@roles_required(ROL_ADMINISTRADOR)
def crear_respaldo_manual():
    usuario = obtener_usuario_actual()
    try:
        resultado = servicio.ejecutar_respaldo(servicio.TIPO_MANUAL, usuario["id_usuario"])
    except servicio.OperacionEnCurso as error:
        return _error(error)
    except servicio.ErrorRespaldo as error:
        _auditar(usuario, ACCION_RESPALDO_FALLIDO, getattr(error, "id_respaldo", None), error.mensaje[:300])
        return _error(error)
    except Exception:
        logger.exception("Error inesperado al ejecutar el respaldo manual")
        return jsonify({"error": "Error interno al ejecutar el respaldo"}), 500

    _auditar(usuario, ACCION_RESPALDO_MANUAL, resultado["id_respaldo"],
             f"archivo={resultado['nombre_archivo']}, bytes={resultado['tamano_bytes']}, "
             f"sha256={resultado['sha256']}")
    return jsonify({
        "message": "Respaldo completado",
        "respaldo": {
            "id_respaldo": resultado["id_respaldo"],
            "nombre_archivo": resultado["nombre_archivo"],
            "tamano_bytes": resultado["tamano_bytes"],
            "sha256": resultado["sha256"],
            "detalle": resultado["detalle"],
        },
    }), 201


@respaldos_bp.route("/respaldos/<int:id_respaldo>/verificar", methods=["POST"])
@roles_required(ROL_ADMINISTRADOR)
def verificar_respaldo(id_respaldo):
    try:
        resumen = servicio.verificar_respaldo(id_respaldo)
    except servicio.ErrorRespaldo as error:
        return _error(error)
    except Exception:
        logger.exception("Error inesperado al verificar el respaldo %s", id_respaldo)
        return jsonify({"error": "Error interno al verificar el respaldo"}), 500
    return jsonify({"message": "El respaldo es íntegro y se puede restaurar", "resumen": resumen}), 200


@respaldos_bp.route("/respaldos/<int:id_respaldo>/restaurar", methods=["POST"])
@roles_required(ROL_ADMINISTRADOR)
def restaurar_respaldo(id_respaldo):
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"error": "La solicitud debe incluir la confirmación y la contraseña."}), 400
    if datos.get("confirmacion") != servicio.CONFIRMACION_RESTAURAR:
        return jsonify({"error": f"Escriba {servicio.CONFIRMACION_RESTAURAR} para confirmar la restauración."}), 400
    clave = datos.get("password")
    if not isinstance(clave, str) or not clave:
        return jsonify({"error": "Ingrese su contraseña para confirmar la restauración."}), 400

    usuario = obtener_usuario_actual()
    if not _clave_valida(usuario["id_usuario"], clave):
        logger.warning("Restauración rechazada: contraseña incorrecta del usuario %s", usuario["id_usuario"])
        return jsonify({"error": "La contraseña no es correcta."}), 403

    try:
        resultado = servicio.ejecutar_restauracion(id_respaldo, usuario["id_usuario"])
    except servicio.OperacionEnCurso as error:
        return _error(error)
    except servicio.ErrorRespaldo as error:
        _auditar(usuario, ACCION_RESTAURACION_FALLIDA, getattr(error, "id_respaldo", None),
                 f"respaldo={id_respaldo}; {error.mensaje}"[:300])
        return _error(error)
    except Exception:
        logger.exception("Error inesperado al restaurar el respaldo %s", id_respaldo)
        return jsonify({"error": "Error interno al restaurar el respaldo"}), 500

    _auditar(usuario, ACCION_RESTAURACION, resultado["id_restauracion"],
             f"respaldo={id_respaldo}; copia_previa={resultado['id_previo']}")
    return jsonify({
        "message": "Restauración completada",
        "id_restauracion": resultado["id_restauracion"],
        "detalle": resultado["detalle"],
        "advertencias": resultado["advertencias"],
    }), 200
