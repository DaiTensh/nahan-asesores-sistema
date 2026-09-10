import json
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify

from backend.config.db import get_connection
from backend.utils.auth import ROL_ADMINISTRADOR, obtener_usuario_actual, roles_required

reportes_blueprint = Blueprint('reportes_blueprint', __name__)
logger = logging.getLogger(__name__)

MENSAJE_SIN_TAREAS = "No se registran tareas para los criterios seleccionados"

# ==========================================================================
# Contrato de respuesta del módulo de reportes (RF31 / RF32).
# Lo consumen Renato Villalobos (RF34, RF38) y Elías Alarcón (RF35): si este
# formato cambia, hay que avisarles antes de tocarlo.
#
# {
#   "cliente" | "responsable": {...datos de la entidad consultada...},
#   "periodo": {"fecha_inicio": "AAAA-MM-DD", "fecha_fin": "AAAA-MM-DD"},
#   "fecha_generacion": "AAAA-MM-DD HH:MM" | null,
#   "tareas": [
#       {id_tarea, titulo, estado, prioridad, fecha_creacion, fecha_vencimiento,
#        id_cliente, cliente, id_responsable, responsable}
#   ],
#   "resumen_por_estado": {"PENDIENTE": n, "EN_PROCESO": n, ...},
#   "mensaje": "..."   -> solo presente cuando no hay tareas en el período
# }
# ==========================================================================


def _validar_periodo(args):
    """Valida y devuelve (fecha_inicio, fecha_fin, error)."""
    fecha_inicio = args.get('fecha_inicio', '').strip()
    fecha_fin = args.get('fecha_fin', '').strip()

    if not fecha_inicio or not fecha_fin:
        return None, None, "Debe indicar fecha_inicio y fecha_fin (formato AAAA-MM-DD)."

    try:
        datetime.strptime(fecha_inicio, "%Y-%m-%d")
        datetime.strptime(fecha_fin, "%Y-%m-%d")
    except ValueError:
        return None, None, "Las fechas deben tener el formato AAAA-MM-DD."

    if fecha_inicio > fecha_fin:
        return None, None, "fecha_inicio no puede ser posterior a fecha_fin."

    return fecha_inicio, fecha_fin, None


def _consultar_tareas_periodo(cursor, fecha_inicio, fecha_fin, id_cliente=None, id_responsable=None):
    """Consulta compartida por RF31 (por cliente) y RF32 (por responsable).

    Filtra tareas por fecha_creacion dentro de [fecha_inicio, fecha_fin]
    (ambos límites inclusive) y, opcionalmente, por cliente o responsable.
    Devuelve (tareas, resumen_por_estado).
    """
    query = """
        SELECT
            t.id_tarea, t.titulo, t.estado, t.prioridad,
            DATE_FORMAT(t.fecha_creacion, '%d-%m-%Y %H:%i') AS fecha_creacion,
            DATE_FORMAT(t.fecha_vencimiento, '%d-%m-%Y') AS fecha_vencimiento,
            c.id_cliente, c.razon_social AS cliente,
            u.id_usuario AS id_responsable, u.nombres AS responsable
        FROM tarea t
        INNER JOIN cliente c ON t.id_cliente = c.id_cliente
        INNER JOIN usuario u ON t.id_responsable = u.id_usuario
        WHERE t.fecha_creacion >= %s AND t.fecha_creacion < DATE_ADD(%s, INTERVAL 1 DAY)
    """
    parametros = [fecha_inicio, fecha_fin]

    if id_cliente:
        query += " AND t.id_cliente = %s"
        parametros.append(id_cliente)

    if id_responsable:
        query += " AND t.id_responsable = %s"
        parametros.append(id_responsable)

    query += " ORDER BY t.fecha_creacion DESC"

    cursor.execute(query, tuple(parametros))
    tareas = cursor.fetchall()

    resumen_por_estado = {}
    for tarea in tareas:
        resumen_por_estado[tarea["estado"]] = resumen_por_estado.get(tarea["estado"], 0) + 1

    return tareas, resumen_por_estado


def _registrar_generacion(cursor, id_usuario, tipo_reporte, parametros):
    """Inserta la generación efectiva en `reporte` y devuelve su fecha."""
    cursor.execute(
        """
        INSERT INTO reporte (id_usuario, tipo_reporte, parametros)
        VALUES (%s, %s, %s)
        """,
        (id_usuario, tipo_reporte, json.dumps(parametros)),
    )
    cursor.execute(
        "SELECT DATE_FORMAT(fecha_generacion, '%d-%m-%Y %H:%i') AS fecha_generacion "
        "FROM reporte WHERE id_reporte = LAST_INSERT_ID()"
    )
    return cursor.fetchone()["fecha_generacion"]


@reportes_blueprint.route('/reportes/tareas-por-cliente', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def reporte_tareas_por_cliente():
    try:
        id_cliente = request.args.get('id_cliente', '').strip()
        if not id_cliente:
            return jsonify({"error": "Debe indicar id_cliente."}), 400

        fecha_inicio, fecha_fin, error = _validar_periodo(request.args)
        if error:
            return jsonify({"error": error}), 400

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión con MySQL."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT id_cliente, rut, razon_social FROM cliente WHERE id_cliente = %s",
                (id_cliente,),
            )
            cliente = cursor.fetchone()
            if not cliente:
                return jsonify({"error": "Cliente inexistente."}), 404

            tareas, resumen_por_estado = _consultar_tareas_periodo(
                cursor, fecha_inicio, fecha_fin, id_cliente=id_cliente
            )

            respuesta = {
                "cliente": cliente,
                "periodo": {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
                "fecha_generacion": None,
                "tareas": tareas,
                "resumen_por_estado": resumen_por_estado,
            }

            if not tareas:
                respuesta["mensaje"] = MENSAJE_SIN_TAREAS
                return jsonify(respuesta), 200

            usuario_actual = obtener_usuario_actual()
            respuesta["fecha_generacion"] = _registrar_generacion(
                cursor,
                usuario_actual["id_usuario"],
                "TAREAS_POR_CLIENTE",
                {"id_cliente": int(id_cliente), "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
            )
            conexion.commit()

        return jsonify(respuesta), 200

    except Exception:
        logger.exception("Error al generar reporte de tareas por cliente")
        return jsonify({"error": "Ocurrió un error al generar el reporte."}), 500


def _a_datetime(valor):
    """Normaliza a `datetime` tanto el datetime que entrega mysql-connector
    como el texto ISO que devuelve SQLite en los tests (mismo criterio que
    `_fecha_a_date` en tareas_routes.py)."""
    if isinstance(valor, str):
        return datetime.strptime(valor[:19], "%Y-%m-%d %H:%M:%S")
    return valor


@reportes_blueprint.route('/reportes/productividad', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def reporte_productividad_por_usuario():
    """RF39 — Visualizando la Productividad por Usuario.

    Por cada usuario activo (filtrable por área): tareas completadas dentro
    del período, tiempo promedio de resolución (entre fecha_creacion y
    fecha_finalizacion — no hay una definición más precisa registrada en
    CU-48 ni en el resto de la documentación, así que se usa este criterio
    por decisión explícita del equipo) y carga vigente (PENDIENTE o
    EN_PROCESO, sin filtrar por período: es una fotografía del momento).
    """
    try:
        fecha_inicio, fecha_fin, error = _validar_periodo(request.args)
        if error:
            return jsonify({"error": error}), 400

        id_area = request.args.get('id_area', '').strip()

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión con MySQL."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            if id_area:
                cursor.execute("SELECT id_area FROM area WHERE id_area = %s", (id_area,))
                if not cursor.fetchone():
                    return jsonify({"error": "Área inexistente."}), 404

            query_usuarios = "SELECT id_usuario, nombres, id_area FROM usuario WHERE estado = 'ACTIVO'"
            parametros_usuarios = []
            if id_area:
                query_usuarios += " AND id_area = %s"
                parametros_usuarios.append(id_area)
            query_usuarios += " ORDER BY nombres"

            cursor.execute(query_usuarios, tuple(parametros_usuarios))
            usuarios = cursor.fetchall()

            acumulado = {
                usuario["id_usuario"]: {"completadas": 0, "segundos_totales": 0}
                for usuario in usuarios
            }
            carga_por_usuario = {}

            if usuarios:
                ids_usuario = [usuario["id_usuario"] for usuario in usuarios]
                marcadores = ", ".join(["%s"] * len(ids_usuario))

                cursor.execute(
                    f"""
                    SELECT id_responsable, fecha_creacion, fecha_finalizacion
                    FROM tarea
                    WHERE estado = 'COMPLETADA'
                      AND id_responsable IN ({marcadores})
                      AND fecha_finalizacion >= %s
                      AND fecha_finalizacion < DATE_ADD(%s, INTERVAL 1 DAY)
                    """,
                    (*ids_usuario, fecha_inicio, fecha_fin)
                )

                for fila in cursor.fetchall():
                    datos = acumulado[fila["id_responsable"]]
                    datos["completadas"] += 1
                    duracion = _a_datetime(fila["fecha_finalizacion"]) - _a_datetime(fila["fecha_creacion"])
                    datos["segundos_totales"] += duracion.total_seconds()

                cursor.execute(
                    f"""
                    SELECT id_responsable, COUNT(*) AS total
                    FROM tarea
                    WHERE estado IN ('PENDIENTE', 'EN_PROCESO')
                      AND id_responsable IN ({marcadores})
                    GROUP BY id_responsable
                    """,
                    tuple(ids_usuario)
                )
                carga_por_usuario = {
                    fila["id_responsable"]: fila["total"] for fila in cursor.fetchall()
                }

            resultado = []
            for usuario in usuarios:
                datos = acumulado[usuario["id_usuario"]]
                promedio_horas = None
                if datos["completadas"] > 0:
                    promedio_horas = round((datos["segundos_totales"] / datos["completadas"]) / 3600, 1)

                resultado.append({
                    "id_usuario": usuario["id_usuario"],
                    "usuario": usuario["nombres"],
                    "tareas_completadas": datos["completadas"],
                    "tiempo_promedio_resolucion_horas": promedio_horas,
                    "carga_vigente": carga_por_usuario.get(usuario["id_usuario"], 0),
                })

            resultado.sort(key=lambda fila: fila["tareas_completadas"], reverse=True)

            respuesta = {
                "periodo": {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
                "usuarios": resultado,
            }

            if not resultado:
                respuesta["mensaje"] = "No hay usuarios activos para los criterios seleccionados"
                return jsonify(respuesta), 200

            usuario_actual = obtener_usuario_actual()
            respuesta["fecha_generacion"] = _registrar_generacion(
                cursor,
                usuario_actual["id_usuario"],
                "PRODUCTIVIDAD_POR_USUARIO",
                {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin, "id_area": id_area or None},
            )
            conexion.commit()

        return jsonify(respuesta), 200

    except Exception:
        logger.exception("Error al generar reporte de productividad por usuario")
        return jsonify({"error": "Ocurrió un error al generar el reporte."}), 500


@reportes_blueprint.route('/reportes/tareas-por-responsable', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def reporte_tareas_por_responsable():
    try:
        id_responsable = request.args.get('id_responsable', '').strip()
        if not id_responsable:
            return jsonify({"error": "Debe indicar id_responsable."}), 400

        fecha_inicio, fecha_fin, error = _validar_periodo(request.args)
        if error:
            return jsonify({"error": error}), 400

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión con MySQL."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT id_usuario, nombres, email FROM usuario WHERE id_usuario = %s",
                (id_responsable,),
            )
            responsable = cursor.fetchone()
            if not responsable:
                return jsonify({"error": "Usuario responsable inexistente."}), 404

            # Misma consulta que RF31; solo cambia el filtro (id_responsable en
            # vez de id_cliente), así que no hay SQL duplicado entre ambos.
            tareas, resumen_por_estado = _consultar_tareas_periodo(
                cursor, fecha_inicio, fecha_fin, id_responsable=id_responsable
            )

            respuesta = {
                "responsable": responsable,
                "periodo": {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
                "fecha_generacion": None,
                "tareas": tareas,
                "resumen_por_estado": resumen_por_estado,
            }

            if not tareas:
                respuesta["mensaje"] = MENSAJE_SIN_TAREAS
                return jsonify(respuesta), 200

            usuario_actual = obtener_usuario_actual()
            respuesta["fecha_generacion"] = _registrar_generacion(
                cursor,
                usuario_actual["id_usuario"],
                "TAREAS_POR_RESPONSABLE",
                {"id_responsable": int(id_responsable), "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
            )
            conexion.commit()

        return jsonify(respuesta), 200

    except Exception:
        logger.exception("Error al generar reporte de tareas por responsable")
        return jsonify({"error": "Ocurrió un error al generar el reporte."}), 500
