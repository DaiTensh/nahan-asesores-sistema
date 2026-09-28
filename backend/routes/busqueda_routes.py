import logging

from flask import Blueprint, jsonify, request

from backend.config.db import get_connection
from backend.utils.auth import ROLES_OPERATIVOS, roles_required

busqueda_bp = Blueprint("busqueda_bp", __name__)
logger = logging.getLogger(__name__)


@busqueda_bp.route("/busqueda-global", methods=["GET"])
@roles_required(*ROLES_OPERATIVOS)
def busqueda_global():
    termino = (request.args.get("q") or request.args.get("termino") or "").strip()

    if not termino:
        return jsonify({
            "error": "Debe indicar un término de búsqueda en el parámetro q."
        }), 400

    conexion = None
    cursor = None

    try:
        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión a la base de datos."}), 500

        cursor = conexion.cursor(dictionary=True)
        patron = f"%{termino}%"

        cursor.execute(
            """
            SELECT
                'cliente' AS tipo,
                c.id_cliente AS id,
                c.razon_social AS nombre,
                c.rut AS detalle
            FROM cliente c
            WHERE c.razon_social LIKE %s OR c.rut LIKE %s
            LIMIT 20
            """,
            (patron, patron),
        )
        clientes = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                'tarea' AS tipo,
                t.id_tarea AS id,
                t.titulo AS nombre,
                t.descripcion AS detalle
            FROM tarea t
            WHERE t.titulo LIKE %s OR t.descripcion LIKE %s
            LIMIT 20
            """,
            (patron, patron),
        )
        tareas = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                'usuario' AS tipo,
                u.id_usuario AS id,
                u.nombres AS nombre,
                u.email AS detalle
            FROM usuario u
            WHERE u.nombres LIKE %s OR u.email LIKE %s
            LIMIT 20
            """,
            (patron, patron),
        )
        usuarios = cursor.fetchall()

        resultados = {
            "clientes": clientes,
            "tareas": tareas,
            "usuarios": usuarios,
        }

        total = sum(len(v) for v in resultados.values())

        return jsonify({
            "termino": termino,
            "total": total,
            "resultados": resultados
        }), 200

    except Exception:
        logger.exception("Error al ejecutar la búsqueda global")
        return jsonify({
            "error": "Error interno al realizar la búsqueda global."
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None:
            conexion.close()