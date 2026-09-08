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

        cursor.execute(
            "SELECT id_tarea FROM tarea WHERE id_tarea = %s",
            (id_tarea,)
        )
        if not cursor.fetchone():
            return jsonify({"error": "Tarea no encontrada"}), 404

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
            UPDATE tarea
            SET id_responsable = %s
            WHERE id_tarea = %s
        """

        cursor.execute(sql, (id_responsable, id_tarea))
        connection.commit()

        # La existencia de la tarea ya se confirmó arriba: si rowcount es 0
        # aquí es porque el responsable nuevo es igual al que ya tenía
        # (MySQL solo cuenta filas realmente modificadas), no porque no
        # exista. Es un no-op válido, no un 404.

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
