"""RF74 — Definiendo la tarifa por hora.

El administrador define la tarifa por hora estándar del sistema (parámetro
TARIFA_HORA_DEFAULT) y, opcionalmente, una tarifa propia por área
(tabla tarifa_hora). El cálculo de RF71-RF75 (control_horas_routes) ya aplica
esta precedencia: tarifa vigente del área y, si no hay, la general. Cada cambio
queda en AUDITORIA; los registros de tiempo ya cerrados conservan la tarifa con
la que se calcularon.

La tarifa por cliente, que el requisito menciona como opcional, no está
implementada: exigiría una columna nueva en tarifa_hora y la regla de
precedencia cliente > área > general.
"""
import logging
import re
from decimal import Decimal

from flask import Blueprint, jsonify, request

from backend.config.db import get_connection
from backend.routes.control_horas_routes import TARIFA_GLOBAL_DEFAULT
from backend.utils.auditoria import registrar_auditoria
from backend.utils.auth import ROL_ADMINISTRADOR, obtener_usuario_actual, roles_required

tarifas_bp = Blueprint("tarifas", __name__)
logger = logging.getLogger(__name__)

PARAMETRO_TARIFA_GENERAL = "TARIFA_HORA_DEFAULT"
PARAMETRO_MONEDA = "MONEDA_DEFAULT"
MONEDA_DEFECTO = "CLP"
TARIFA_MAXIMA = Decimal("10000000")
_PATRON_MONTO = re.compile(r"^[0-9]{1,8}(\.[0-9]{1,2})?\Z")

ACCION_TARIFA_GENERAL = "CONFIGURAR_TARIFA_GENERAL"
ACCION_TARIFA_AREA_DEFINIDA = "TARIFA_AREA_DEFINIDA"
ACCION_TARIFA_AREA_ELIMINADA = "TARIFA_AREA_ELIMINADA"

_VIGENTE = """
    t2.id_area = a.id_area AND t2.estado = 'ACTIVA' AND t2.fecha_inicio <= CURRENT_DATE
    AND (t2.fecha_fin IS NULL OR t2.fecha_fin >= CURRENT_DATE)
"""
_SQL_AREAS_CON_TARIFA = f"""
    SELECT a.id_area, a.nombre_area, t.id_tarifa, t.valor_hora, t.fecha_inicio
    FROM area a
    LEFT JOIN tarifa_hora t ON t.id_tarifa = (
        SELECT t2.id_tarifa FROM tarifa_hora t2 WHERE {_VIGENTE}
        ORDER BY t2.fecha_inicio DESC, t2.id_tarifa DESC LIMIT 1
    )
    ORDER BY a.id_area
"""


def leer_valor_hora(valor):
    """Decimal con la tarifa indicada, o None si no es un monto válido (0 < monto <= 10 millones, 2 decimales)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
        return None
    texto = str(valor).strip()
    if not _PATRON_MONTO.match(texto):
        return None
    monto = Decimal(texto)
    return monto if 0 < monto <= TARIFA_MAXIMA else None


def _texto_monto(monto):
    return f"{Decimal(monto):.2f}"


def _leer_parametro(cursor, nombre):
    cursor.execute("SELECT valor_parametro FROM parametros_sistema WHERE nombre_parametro = %s", (nombre,))
    fila = cursor.fetchone()
    return fila["valor_parametro"] if fila else None


def _tarifa_general(cursor):
    try:
        return Decimal(_leer_parametro(cursor, PARAMETRO_TARIFA_GENERAL))
    except Exception:
        return TARIFA_GLOBAL_DEFAULT


def _moneda(cursor):
    return _leer_parametro(cursor, PARAMETRO_MONEDA) or MONEDA_DEFECTO


def _respuesta_valor_invalido():
    maximo = f"{int(TARIFA_MAXIMA):,}".replace(",", ".")
    return jsonify({"error": f"La tarifa debe ser un monto mayor que cero, de hasta {maximo} y con a lo sumo dos decimales."}), 400


def _con_cursor(operacion):
    """Ejecuta `operacion(cursor, connection)` con conexión propia y devuelve (respuesta, estado)."""
    connection = cursor = None
    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "Error de conexión con la base de datos"}), 500
        cursor = connection.cursor(dictionary=True)
        return operacion(cursor, connection)
    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al procesar una tarifa")
        return jsonify({"error": "Error interno al procesar la tarifa"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tarifas_bp.route("/tarifas", methods=["GET"])
@roles_required(ROL_ADMINISTRADOR)
def obtener_tarifas():
    def operacion(cursor, connection):
        general = _tarifa_general(cursor)
        moneda = _moneda(cursor)
        cursor.execute(_SQL_AREAS_CON_TARIFA)
        areas = [{
            "id_area": fila["id_area"],
            "nombre_area": fila["nombre_area"],
            "valor_hora": float(fila["valor_hora"]) if fila["valor_hora"] is not None else None,
            "vigente_desde": fila["fecha_inicio"].strftime("%Y-%m-%d") if fila["fecha_inicio"] is not None else None,
            "tarifa_aplicada": float(fila["valor_hora"] if fila["valor_hora"] is not None else general),
        } for fila in cursor.fetchall()]
        return jsonify({"general": {"valor_hora": float(general), "moneda": moneda}, "areas": areas}), 200
    return _con_cursor(operacion)


@tarifas_bp.route("/tarifas/general", methods=["PUT"])
@roles_required(ROL_ADMINISTRADOR)
def definir_tarifa_general():
    datos = request.get_json(silent=True)
    monto = leer_valor_hora(datos.get("valor_hora") if isinstance(datos, dict) else None)
    if monto is None:
        return _respuesta_valor_invalido()
    usuario = obtener_usuario_actual()

    def operacion(cursor, connection):
        anterior = _leer_parametro(cursor, PARAMETRO_TARIFA_GENERAL)
        if anterior is None:
            cursor.execute(
                "INSERT INTO parametros_sistema (nombre_parametro, valor_parametro, tipo_dato, descripcion) "
                "VALUES (%s, %s, 'DECIMAL', 'Tarifa global por hora utilizada cuando no existe una tarifa vigente para el área')",
                (PARAMETRO_TARIFA_GENERAL, _texto_monto(monto)),
            )
        else:
            cursor.execute("UPDATE parametros_sistema SET valor_parametro = %s WHERE nombre_parametro = %s",
                           (_texto_monto(monto), PARAMETRO_TARIFA_GENERAL))
        registrar_auditoria(
            cursor, usuario["id_usuario"], "parametros_sistema", ACCION_TARIFA_GENERAL,
            datos_anteriores=f"{PARAMETRO_TARIFA_GENERAL}={anterior}", datos_nuevos=f"{PARAMETRO_TARIFA_GENERAL}={_texto_monto(monto)}",
        )
        connection.commit()
        return jsonify({"message": "Tarifa general actualizada", "valor_hora": float(monto)}), 200
    return _con_cursor(operacion)


def _tarifa_vigente_del_area(cursor, id_area):
    cursor.execute(
        "SELECT t2.id_tarifa, t2.valor_hora FROM tarifa_hora t2, (SELECT %s AS id_area) a "
        f"WHERE {_VIGENTE} ORDER BY t2.fecha_inicio DESC, t2.id_tarifa DESC LIMIT 1",
        (id_area,),
    )
    return cursor.fetchone()


def _cerrar_tarifas_activas(cursor, id_area):
    """Conserva el historial: las tarifas activas del área pasan a INACTIVA con fecha de término hoy."""
    cursor.execute(
        "UPDATE tarifa_hora SET estado = 'INACTIVA', fecha_fin = CURRENT_DATE WHERE id_area = %s AND estado = 'ACTIVA'",
        (id_area,),
    )


@tarifas_bp.route("/tarifas/areas/<int:id_area>", methods=["PUT"])
@roles_required(ROL_ADMINISTRADOR)
def definir_tarifa_de_area(id_area):
    datos = request.get_json(silent=True)
    monto = leer_valor_hora(datos.get("valor_hora") if isinstance(datos, dict) else None)
    if monto is None:
        return _respuesta_valor_invalido()
    usuario = obtener_usuario_actual()

    def operacion(cursor, connection):
        cursor.execute("SELECT id_area FROM area WHERE id_area = %s", (id_area,))
        if not cursor.fetchone():
            return jsonify({"error": "El área indicada no existe"}), 404
        anterior = _tarifa_vigente_del_area(cursor, id_area)
        _cerrar_tarifas_activas(cursor, id_area)
        cursor.execute(
            "INSERT INTO tarifa_hora (id_area, valor_hora, moneda, fecha_inicio, descripcion, estado) "
            "VALUES (%s, %s, %s, CURRENT_DATE, 'Definida desde la aplicación', 'ACTIVA')",
            (id_area, _texto_monto(monto), _moneda(cursor)),
        )
        id_tarifa = cursor.lastrowid
        registrar_auditoria(
            cursor, usuario["id_usuario"], "tarifa_hora", ACCION_TARIFA_AREA_DEFINIDA, id_registro=id_tarifa,
            datos_anteriores=f"id_area={id_area}, valor_hora={_texto_monto(anterior['valor_hora'])}" if anterior else None,
            datos_nuevos=f"id_area={id_area}, valor_hora={_texto_monto(monto)}",
        )
        connection.commit()
        return jsonify({"message": "Tarifa del área actualizada", "id_area": id_area, "valor_hora": float(monto)}), 200
    return _con_cursor(operacion)


@tarifas_bp.route("/tarifas/areas/<int:id_area>", methods=["DELETE"])
@roles_required(ROL_ADMINISTRADOR)
def quitar_tarifa_de_area(id_area):
    usuario = obtener_usuario_actual()

    def operacion(cursor, connection):
        anterior = _tarifa_vigente_del_area(cursor, id_area)
        if not anterior:
            return jsonify({"error": "El área no tiene una tarifa propia: ya usa la tarifa general"}), 404
        _cerrar_tarifas_activas(cursor, id_area)
        registrar_auditoria(
            cursor, usuario["id_usuario"], "tarifa_hora", ACCION_TARIFA_AREA_ELIMINADA, id_registro=anterior["id_tarifa"],
            datos_anteriores=f"id_area={id_area}, valor_hora={_texto_monto(anterior['valor_hora'])}",
            datos_nuevos=f"id_area={id_area}, usa la tarifa general",
        )
        connection.commit()
        return jsonify({"message": "El área volvió a usar la tarifa general", "id_area": id_area}), 200
    return _con_cursor(operacion)
