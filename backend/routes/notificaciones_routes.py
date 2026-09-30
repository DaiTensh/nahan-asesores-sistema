"""Notificaciones internas (RF51, RF52, RF53).

Expone `crear_notificacion`, la función acordada en la coordinación del
Incremento 2 (ver `docs/incremento2/equipo.json`): Matías Rodríguez (RF16) y
Renato Villalobos (RF26) la consumen desde sus propios módulos para no volver
a duplicar el INSERT a la tabla `notificacion`.

Las rutas de este archivo son la consulta mínima que cierra RF51–RF53: sin
ellas los avisos quedaban guardados pero el usuario no podía verlos. Cada
usuario solo ve y marca sus propias notificaciones; una ajena responde 404,
igual que una inexistente, para no revelar que existe. El contrato coincide
con el previsto para RF46 (Incremento 3), que lo amplía con niveles de
importancia y alertas en el panel.

RF46: cada notificación lleva tipo e importancia. Los niveles son los de las
fichas del sprint: CRITICA (se destaca en la bandeja), ALTA y NORMAL, que es
el valor por defecto. Quien genera el aviso indica la importancia según el
evento. Toda notificación se escribe con `crear_notificacion`: no hay otra
vía de INSERT.
"""
import logging

from flask import Blueprint, jsonify, request

from backend.config.db import get_connection
from backend.utils.auth import login_required, obtener_usuario_actual

notificaciones_bp = Blueprint("notificaciones", __name__)
logger = logging.getLogger(__name__)

LIMITE_POR_DEFECTO = 20
LIMITE_MAXIMO = 100

IMPORTANCIA_NORMAL = "NORMAL"
IMPORTANCIA_ALTA = "ALTA"
IMPORTANCIA_CRITICA = "CRITICA"
IMPORTANCIAS = (IMPORTANCIA_NORMAL, IMPORTANCIA_ALTA, IMPORTANCIA_CRITICA)

# Importancia que cada evento da a su aviso (fichas del Incremento 3):
#   CRITICA: tarea enviada a revisión (a administradores) y seguridad.
#   ALTA:    asignación y reasignación de tareas.
#   NORMAL:  el resto (cambio de estado, resultado de la revisión, vencimiento).


def crear_notificacion(cursor, id_usuario, tipo, mensaje, url_destino=None, id_usuario_actor=None,
                       importancia=IMPORTANCIA_NORMAL):
    """Inserta un aviso en `notificacion` para `id_usuario`.

    `importancia` es NORMAL (por defecto), ALTA o CRITICA; cualquier otro
    valor es un error de programación y se rechaza antes de escribir.

    Si `id_usuario_actor` coincide con `id_usuario` no se inserta nada: el
    criterio de aceptación de RF52 pide no notificar a quien ejecuta la
    acción sobre sí mismo, y el mismo criterio es razonable para RF51 (no
    tiene sentido avisarle a alguien de un cambio que hizo él mismo).
    """
    if importancia not in IMPORTANCIAS:
        raise ValueError(f"Importancia de notificación no válida: {importancia!r}")

    if id_usuario_actor is not None and id_usuario_actor == id_usuario:
        return

    cursor.execute(
        """
        INSERT INTO notificacion (id_usuario, tipo, importancia, mensaje, url_destino)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (id_usuario, tipo, importancia, mensaje, url_destino)
    )


def _contar_no_leidas(cursor, id_usuario):
    cursor.execute(
        "SELECT COUNT(*) AS total FROM notificacion WHERE id_usuario = %s AND leida = FALSE",
        (id_usuario,)
    )
    fila = cursor.fetchone()
    return int(fila["total"]) if fila else 0


@notificaciones_bp.route("/notificaciones", methods=["GET"])
@login_required
def listar_notificaciones():
    usuario = obtener_usuario_actual()

    solo_no_leidas = request.args.get("solo_no_leidas", "").strip().lower() in {"1", "true", "si", "sí"}
    limite_texto = request.args.get("limite", str(LIMITE_POR_DEFECTO)).strip()

    if not limite_texto.isdecimal() or int(limite_texto) < 1:
        return jsonify({"error": "limite debe ser un entero positivo"}), 400

    limite = min(int(limite_texto), LIMITE_MAXIMO)

    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        condiciones = ["id_usuario = %s"]
        parametros = [usuario["id_usuario"]]
        if solo_no_leidas:
            condiciones.append("leida = FALSE")

        cursor.execute(
            f"""
            SELECT id_notificacion, tipo, importancia, mensaje, url_destino, fecha, leida
            FROM notificacion
            WHERE {" AND ".join(condiciones)}
            ORDER BY fecha DESC, id_notificacion DESC
            LIMIT %s
            """,
            (*parametros, limite)
        )
        notificaciones = cursor.fetchall()
        for notificacion in notificaciones:
            notificacion["leida"] = bool(notificacion["leida"])

        no_leidas = _contar_no_leidas(cursor, usuario["id_usuario"])

        return jsonify({"notificaciones": notificaciones, "no_leidas": no_leidas}), 200

    except Exception:
        logger.exception("Error al listar notificaciones")
        return jsonify({"error": "Error interno al listar las notificaciones"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@notificaciones_bp.route("/notificaciones/contador", methods=["GET"])
@login_required
def contar_notificaciones_no_leidas():
    usuario = obtener_usuario_actual()
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        return jsonify({"no_leidas": _contar_no_leidas(cursor, usuario["id_usuario"])}), 200

    except Exception:
        logger.exception("Error al contar notificaciones")
        return jsonify({"error": "Error interno al contar las notificaciones"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@notificaciones_bp.route("/notificaciones/<int:id_notificacion>/leida", methods=["PUT"])
@login_required
def marcar_notificacion_leida(id_notificacion):
    usuario = obtener_usuario_actual()
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        # El filtro por id_usuario es la autorización: una notificación de
        # otro usuario no se encuentra, igual que una inexistente.
        cursor.execute(
            "SELECT id_notificacion FROM notificacion WHERE id_notificacion = %s AND id_usuario = %s",
            (id_notificacion, usuario["id_usuario"])
        )
        if not cursor.fetchone():
            return jsonify({"error": "Notificación no encontrada"}), 404

        cursor.execute(
            "UPDATE notificacion SET leida = TRUE WHERE id_notificacion = %s AND id_usuario = %s",
            (id_notificacion, usuario["id_usuario"])
        )
        no_leidas = _contar_no_leidas(cursor, usuario["id_usuario"])
        connection.commit()

        return jsonify({"message": "Notificación marcada como leída", "no_leidas": no_leidas}), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al marcar notificación como leída")
        return jsonify({"error": "Error interno al actualizar la notificación"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@notificaciones_bp.route("/notificaciones/leer-todas", methods=["PUT"])
@login_required
def marcar_todas_leidas():
    usuario = obtener_usuario_actual()
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "UPDATE notificacion SET leida = TRUE WHERE id_usuario = %s AND leida = FALSE",
            (usuario["id_usuario"],)
        )
        marcadas = cursor.rowcount
        connection.commit()

        return jsonify({"message": "Notificaciones marcadas como leídas", "marcadas": marcadas, "no_leidas": 0}), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al marcar todas las notificaciones como leídas")
        return jsonify({"error": "Error interno al actualizar las notificaciones"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
