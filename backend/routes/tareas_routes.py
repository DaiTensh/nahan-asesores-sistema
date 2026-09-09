import logging

from flask import Blueprint, request, jsonify
from backend.config.db import get_connection
from backend.utils.auth import ROL_ADMINISTRADOR, login_required, obtener_usuario_actual

tareas_bp = Blueprint("tareas", __name__)
logger = logging.getLogger(__name__)

ESTADOS_FINALES = {"COMPLETADA", "CANCELADA"}


@tareas_bp.route("/tareas", methods=["POST"])
@login_required
def crear_tarea():
    connection = None
    cursor = None
    data = request.get_json()

    id_cliente = data.get("id_cliente")
    id_area = data.get("id_area")
    areas = data.get("areas")
    id_responsable = data.get("id_responsable")
    id_creador = obtener_usuario_actual()["id_usuario"]
    titulo = data.get("titulo")
    descripcion = data.get("descripcion")
    prioridad = data.get("prioridad", "MEDIA")
    fecha_vencimiento = data.get("fecha_vencimiento")

    if areas is None:
        areas = [1, 2] if id_area == "AMBAS" else [id_area]

    try:
        areas = list(dict.fromkeys(int(area) for area in areas if area))
    except (TypeError, ValueError):
        return jsonify({"error": "El área seleccionada no es válida"}), 400

    if not id_cliente or not areas or not id_responsable or not id_creador or not titulo:
        return jsonify({"error": "Los campos obligatorios no están completos"}), 400

    if any(area not in [1, 2] for area in areas):
        return jsonify({"error": "El área seleccionada no es válida"}), 400

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT id_usuario, estado
            FROM usuario
            WHERE id_usuario = %s
            """,
            (id_responsable,)
        )
        responsable = cursor.fetchone()

        if not responsable or responsable[1] != "ACTIVO":
            return jsonify({"error": "El responsable seleccionado no es válido"}), 422

        sql = """
            INSERT INTO tarea (
                id_cliente,
                id_area,
                id_responsable,
                id_creador,
                titulo,
                descripcion,
                prioridad,
                fecha_vencimiento
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        for area in areas:
            values = (
                id_cliente,
                area,
                id_responsable,
                id_creador,
                titulo,
                descripcion,
                prioridad,
                fecha_vencimiento
            )

            cursor.execute(sql, values)

        connection.commit()

        mensaje = "Tarea creada correctamente"
        if len(areas) > 1:
            mensaje = "Tareas creadas correctamente"

        return jsonify({
            "message": mensaje
        }), 201

    except Exception:
        logger.exception("Error al crear tarea")
        return jsonify({"error": "Error interno al crear tarea"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/pendientes", methods=["GET"])
@login_required
def listar_tareas_pendientes():
    connection = None
    cursor = None
    usuario = obtener_usuario_actual()

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        condiciones = ["t.estado IN ('PENDIENTE', 'EN_PROCESO', 'EN_REVISION')"]
        parametros = []

        # Un usuario no administrador solo debe ver sus propias tareas: el
        # frontend (tareas.js) ya filtraba esto en el navegador, pero eso no
        # impedía que cualquier autenticado pidiera este endpoint directo y
        # recibiera las tareas de todas las áreas. Se aplica la misma regla
        # en el servidor.
        if usuario["nombre_rol"] != ROL_ADMINISTRADOR:
            condiciones.append("t.id_responsable = %s")
            parametros.append(usuario["id_usuario"])

        sql = f"""
            SELECT
                t.id_tarea,
                t.id_responsable,
                t.titulo,
                t.descripcion,
                t.estado,
                t.prioridad,
                t.fecha_vencimiento,
                c.razon_social AS cliente,
                u.nombres AS responsable,
                a.nombre_area AS area
            FROM tarea t
            INNER JOIN cliente c ON t.id_cliente = c.id_cliente
            INNER JOIN usuario u ON t.id_responsable = u.id_usuario
            INNER JOIN area a ON t.id_area = a.id_area
            WHERE {" AND ".join(condiciones)}
            ORDER BY t.fecha_vencimiento ASC
        """

        cursor.execute(sql, tuple(parametros))
        tareas = cursor.fetchall()

        return jsonify(tareas), 200

    except Exception:
        logger.exception("Error al listar tareas pendientes")
        return jsonify({"error": "Error interno al listar tareas"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def _reasignar_tarea(cursor, id_tarea, id_responsable):
    """Mueve una tarea a un nuevo responsable.

    Usada tanto por la reasignación individual (RF16) como por la
    redistribución masiva (RF19): ambas comparten la misma validación y el
    mismo UPDATE, para que no puedan divergir.

    Devuelve (ok, error, status, id_responsable_anterior).
    """
    cursor.execute(
        "SELECT id_responsable FROM tarea WHERE id_tarea = %s",
        (id_tarea,)
    )
    tarea = cursor.fetchone()

    if not tarea:
        return False, "Tarea no encontrada", 404, None

    id_responsable_anterior = tarea[0]

    cursor.execute(
        """
        SELECT id_usuario, estado
        FROM usuario
        WHERE id_usuario = %s
        """,
        (id_responsable,)
    )
    responsable = cursor.fetchone()

    if not responsable or responsable[1] != "ACTIVO":
        return False, "El responsable seleccionado no es válido", 422, None

    cursor.execute(
        """
        UPDATE tarea
        SET id_responsable = %s
        WHERE id_tarea = %s
        """,
        (id_responsable, id_tarea)
    )

    return True, None, None, id_responsable_anterior


@tareas_bp.route("/tareas/<int:id_tarea>/asignar", methods=["PUT"])
@login_required
def asignar_tarea(id_tarea):
    connection = None
    cursor = None
    data = request.get_json()

    id_responsable = data.get("id_responsable")

    if not id_responsable:
        return jsonify({"error": "Debe seleccionar un responsable"}), 400

    try:
        connection = get_connection()
        cursor = connection.cursor()

        ok, error, status, _ = _reasignar_tarea(cursor, id_tarea, id_responsable)

        if not ok:
            return jsonify({"error": error}), status

        connection.commit()

        # La existencia de la tarea ya se confirmó dentro de _reasignar_tarea:
        # si rowcount es 0 aquí es porque el responsable nuevo es igual al
        # que ya tenía (MySQL solo cuenta filas realmente modificadas), no
        # porque no exista. Es un no-op válido, no un 404.

        return jsonify({"message": "Tarea asignada correctamente"}), 200

    except Exception:
        logger.exception("Error al asignar tarea")
        return jsonify({"error": "Error interno al asignar tarea"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/<int:id_tarea>/estado", methods=["PUT"])
@login_required
def actualizar_estado_tarea(id_tarea):
    connection = None
    cursor = None
    data = request.get_json()
    usuario = obtener_usuario_actual()

    estado = data.get("estado")

    estados_validos = [
        "PENDIENTE",
        "EN_PROCESO",
        "EN_REVISION",
        "COMPLETADA",
        "CANCELADA"
    ]

    if estado not in estados_validos:
        return jsonify({"error": "Estado no válido"}), 400

    if estado in ESTADOS_FINALES and usuario["nombre_rol"] != ROL_ADMINISTRADOR:
        return jsonify({
            "error": "Solo un administrador puede aplicar estados finales"
        }), 403

    try:
        connection = get_connection()
        cursor = connection.cursor()

        sql = """
            UPDATE tarea
            SET estado = %s
            WHERE id_tarea = %s
        """

        cursor.execute(sql, (estado, id_tarea))
        connection.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Tarea no encontrada"}), 404

        return jsonify({"message": "Estado actualizado correctamente"}), 200

    except Exception:
        logger.exception("Error al actualizar estado de tarea")
        return jsonify({"error": "Error interno al actualizar estado"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/<int:id_tarea>/prioridad", methods=["PUT"])
@login_required
def actualizar_prioridad_tarea(id_tarea):
    connection = None
    cursor = None
    data = request.get_json()

    prioridad = data.get("prioridad")

    prioridades_validas = [
        "BAJA",
        "MEDIA",
        "ALTA",
        "URGENTE"
    ]

    if prioridad not in prioridades_validas:
        return jsonify({"error": "Prioridad no válida"}), 400

    try:
        connection = get_connection()
        cursor = connection.cursor()

        sql = """
            UPDATE tarea
            SET prioridad = %s
            WHERE id_tarea = %s
        """

        cursor.execute(sql, (prioridad, id_tarea))
        connection.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Tarea no encontrada"}), 404

        return jsonify({"message": "Prioridad actualizada correctamente"}), 200

    except Exception:
        logger.exception("Error al actualizar prioridad de tarea")
        return jsonify({"error": "Error interno al actualizar prioridad"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/carga", methods=["GET"])
@login_required
def carga_trabajo():
    """Cantidad de tareas no finalizadas por responsable.

    RF19: se consulta antes de confirmar una redistribución, para mostrar la
    carga de origen y de destino.
    """
    connection = None
    cursor = None

    ids_usuario_texto = request.args.get("ids_usuario", "")

    try:
        ids_usuario = list(dict.fromkeys(
            int(id_texto) for id_texto in ids_usuario_texto.split(",") if id_texto.strip()
        ))
    except ValueError:
        return jsonify({"error": "ids_usuario debe ser una lista de números separados por coma"}), 400

    if not ids_usuario:
        return jsonify({"error": "Debe indicar al menos un id_usuario"}), 400

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        marcadores = ", ".join(["%s"] * len(ids_usuario))
        cursor.execute(
            f"""
            SELECT id_responsable, COUNT(*) AS total
            FROM tarea
            WHERE id_responsable IN ({marcadores})
              AND estado NOT IN ('COMPLETADA', 'CANCELADA')
            GROUP BY id_responsable
            """,
            tuple(ids_usuario)
        )
        conteos = {fila["id_responsable"]: fila["total"] for fila in cursor.fetchall()}

        carga = {str(id_usuario): conteos.get(id_usuario, 0) for id_usuario in ids_usuario}

        return jsonify(carga), 200

    except Exception:
        logger.exception("Error al consultar la carga de trabajo")
        return jsonify({"error": "Error interno al consultar la carga de trabajo"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/reasignar-masivo", methods=["PUT"])
@login_required
def reasignar_tareas_masivo():
    """RF19 — Reasignando y Redistribuyendo Tareas.

    Mueve varias tareas a un nuevo responsable en una sola operación,
    reutilizando la misma validación que la reasignación individual (RF16) y
    dejando cada movimiento en auditoria.
    """
    connection = None
    cursor = None
    data = request.get_json()
    usuario = obtener_usuario_actual()

    ids_tarea = data.get("ids_tarea")
    id_responsable = data.get("id_responsable")

    if not isinstance(ids_tarea, list) or not ids_tarea:
        return jsonify({"error": "Debe seleccionar al menos una tarea"}), 400

    if not id_responsable:
        return jsonify({"error": "Debe seleccionar un responsable"}), 400

    try:
        ids_tarea = list(dict.fromkeys(int(id_tarea) for id_tarea in ids_tarea))
    except (TypeError, ValueError):
        return jsonify({"error": "La lista de tareas no es válida"}), 400

    try:
        connection = get_connection()
        cursor = connection.cursor()

        reasignadas = 0

        for id_tarea in ids_tarea:
            ok, error, status, id_responsable_anterior = _reasignar_tarea(
                cursor, id_tarea, id_responsable
            )

            if not ok:
                connection.rollback()
                return jsonify({
                    "error": f"Tarea {id_tarea}: {error}"
                }), status

            cursor.execute(
                """
                INSERT INTO auditoria (id_usuario, tabla_afectada, accion, datos_anteriores, datos_nuevos)
                VALUES (%s, 'tarea', 'REASIGNACION_MASIVA', %s, %s)
                """,
                (
                    usuario["id_usuario"],
                    f"id_tarea={id_tarea}, id_responsable={id_responsable_anterior}",
                    f"id_tarea={id_tarea}, id_responsable={id_responsable}"
                )
            )
            reasignadas += 1

        connection.commit()

        return jsonify({
            "message": f"{reasignadas} tarea(s) reasignada(s) correctamente",
            "reasignadas": reasignadas
        }), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al reasignar tareas de forma masiva")
        return jsonify({"error": "Error interno al reasignar las tareas"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
