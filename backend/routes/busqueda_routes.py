import logging

from flask import Blueprint, jsonify, request

from backend.config.db import get_connection
from backend.utils.auth import ROL_ADMINISTRADOR, ROLES_OPERATIVOS, obtener_usuario_actual, roles_required

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

    if len(termino) < 2:
        return jsonify({
            "error": "La búsqueda debe tener al menos 2 caracteres."
        }), 400

    conexion = None
    cursor = None

    try:
        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión a la base de datos."}), 500

        usuario = obtener_usuario_actual()
        es_admin = usuario and usuario.get("nombre_rol") == ROL_ADMINISTRADOR
        patron = f"%{termino}%"
        cursor = conexion.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                'cliente' AS tipo,
                c.id_cliente AS id,
                c.razon_social AS nombre,
                c.rut AS detalle
            FROM cliente c
            WHERE c.razon_social LIKE %s OR c.rut LIKE %s
            ORDER BY c.razon_social ASC
            LIMIT 20
            """,
            (patron, patron),
        )
        clientes = cursor.fetchall()

        sql_tareas = """
            SELECT
                'tarea' AS tipo,
                t.id_tarea AS id,
                t.titulo AS nombre,
                t.descripcion AS detalle,
                t.id_responsable AS id_responsable
            FROM tarea t
            WHERE (t.titulo LIKE %s OR t.descripcion LIKE %s)
        """
        params_tareas = [patron, patron]
        if not es_admin:
            sql_tareas += " AND t.id_responsable = %s"
            params_tareas.append(usuario["id_usuario"])
        sql_tareas += " ORDER BY t.fecha_creacion DESC LIMIT 20"
        cursor.execute(sql_tareas, tuple(params_tareas))
        tareas = cursor.fetchall()

        sql_usuarios = """
            SELECT
                'usuario' AS tipo,
                u.id_usuario AS id,
                u.nombres AS nombre,
                u.email AS detalle
            FROM usuario u
            WHERE (u.nombres LIKE %s OR u.email LIKE %s)
        """
        params_usuarios = [patron, patron]
        if not es_admin:
            sql_usuarios += " AND u.id_usuario = %s"
            params_usuarios.append(usuario["id_usuario"])
        sql_usuarios += " ORDER BY u.nombres ASC LIMIT 20"
        cursor.execute(sql_usuarios, tuple(params_usuarios))
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