from flask import Blueprint, request, jsonify
from backend.config.db import get_connection

tareas_bp = Blueprint("tareas", __name__)


@tareas_bp.route("/tareas", methods=["POST"])
def crear_tarea():
    data = request.get_json()

    id_cliente = data.get("id_cliente")
    id_area = data.get("id_area")
    id_responsable = data.get("id_responsable")
    id_creador = data.get("id_creador")
    titulo = data.get("titulo")
    descripcion = data.get("descripcion")
    prioridad = data.get("prioridad", "MEDIA")
    fecha_vencimiento = data.get("fecha_vencimiento")

    if not id_cliente or not id_area or not id_responsable or not id_creador or not titulo:
        return jsonify({"error": "Los campos obligatorios no están completos"}), 400

    try:
        connection = get_connection()
        cursor = connection.cursor()

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

        values = (
            id_cliente,
            id_area,
            id_responsable,
            id_creador,
            titulo,
            descripcion,
            prioridad,
            fecha_vencimiento
        )

        cursor.execute(sql, values)
        connection.commit()

        return jsonify({
            "message": "Tarea creada correctamente"
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/pendientes", methods=["GET"])
def listar_tareas_pendientes():
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        sql = """
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
            WHERE t.estado IN ('PENDIENTE', 'EN_PROCESO', 'EN_REVISION')
            ORDER BY t.fecha_vencimiento ASC
        """

        cursor.execute(sql)
        tareas = cursor.fetchall()

        return jsonify(tareas), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/<int:id_tarea>/asignar", methods=["PUT"])
def asignar_tarea(id_tarea):
    data = request.get_json()

    id_responsable = data.get("id_responsable")

    if not id_responsable:
        return jsonify({"error": "Debe seleccionar un responsable"}), 400

    try:
        connection = get_connection()
        cursor = connection.cursor()

        sql = """
            UPDATE tarea
            SET id_responsable = %s
            WHERE id_tarea = %s
        """

        cursor.execute(sql, (id_responsable, id_tarea))
        connection.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Tarea no encontrada"}), 404

        return jsonify({"message": "Tarea asignada correctamente"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/<int:id_tarea>/estado", methods=["PUT"])
def actualizar_estado_tarea(id_tarea):
    data = request.get_json()

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

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/<int:id_tarea>/prioridad", methods=["PUT"])
def actualizar_prioridad_tarea(id_tarea):
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

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()