import io
import json
import logging
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle

from flask import Blueprint, request, jsonify, send_file
from openpyxl import Workbook

from backend.config.db import get_connection
from backend.utils.auditoria import consultar_auditoria, modulos_disponibles, tablas_de_modulo
from backend.utils.auth import ROL_ADMINISTRADOR, obtener_usuario_actual, roles_required

reportes_blueprint = Blueprint('reportes_blueprint', __name__)
logger = logging.getLogger(__name__)

MENSAJE_SIN_TAREAS = "No se registran tareas para los criterios seleccionados"
MENSAJE_SIN_COMPLETADAS = "No se registran tareas completadas en el período seleccionado"

# ==========================================================================
# Contrato de respuesta del módulo de reportes (RF31 / RF32).
# Lo consumen Renato Villalobos (RF34, RF38) y Elías Alarcón (RF35): si este
# formato cambia, hay que avisarles antes de tocarlo.
#
# {
#   "cliente" | "responsable": {...datos de la entidad consultada...},
#   "periodo": {"fecha_inicio": "AAAA-MM-DD", "fecha_fin": "AAAA-MM-DD"},
#   "id_reporte": 123 | null,          -> ausente/null cuando no hay tareas
#   "fecha_generacion": "AAAA-MM-DD HH:MM" | null,
#   "tareas": [
#       {id_tarea, titulo, estado, prioridad, fecha_creacion, fecha_vencimiento,
#        id_cliente, cliente, id_responsable, responsable}
#   ],
#   "resumen_por_estado": {"PENDIENTE": n, "EN_PROCESO": n, ...},
#   "mensaje": "..."   -> solo presente cuando no hay tareas en el período
# }
#
# "id_reporte" es la clave para exportar (GET /reportes/<id_reporte>/excel,
# RF35; también el PDF de RF34): con él y los parámetros ya
# guardados en la tabla `reporte` se vuelve a consultar la base en vez de
# convertir el HTML ya renderizado. Ver _datos_para_exportar más abajo.
# ==========================================================================


def _validar_periodo(args):
    """Valida y devuelve (fecha_inicio, fecha_fin, error)."""
    fecha_inicio = args.get('fecha_inicio', '').strip()
    fecha_fin = args.get('fecha_fin', '').strip()

    if not fecha_inicio or not fecha_fin:
        return None, None, "Debe indicar fecha_inicio y fecha_fin (formato AAAA-MM-DD)."

    try:
        fecha_inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d").date().isoformat()
        fecha_fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None, None, "Las fechas deben tener el formato AAAA-MM-DD."

    if fecha_inicio > fecha_fin:
        return None, None, "fecha_inicio no puede ser posterior a fecha_fin."

    return fecha_inicio, fecha_fin, None


# RF38 — atajos de período. La clave llega desde el selector «Período rápido»
# del frontend y se guarda en `reporte.parametros` junto con las fechas, para
# que el PDF y el Excel digan qué período se aplicó sin depender del nombre
# del archivo. Solo se aceptan estas claves.
ETIQUETAS_PERIODO = {
    "semana": "Última semana",
    "mes": "Último mes",
    "anio": "Año actual",
}


def _etiqueta_periodo(args):
    """Devuelve (clave, error). La clave es None cuando el período fue
    elegido a mano."""
    clave = (args.get("periodo_etiqueta") or "").strip()
    if not clave:
        return None, None
    if clave not in ETIQUETAS_PERIODO:
        return None, "periodo_etiqueta no es válido."
    return clave, None


def _texto_periodo(parametros):
    texto = f"{parametros.get('fecha_inicio')} a {parametros.get('fecha_fin')}"
    etiqueta = ETIQUETAS_PERIODO.get(parametros.get("periodo_etiqueta"))
    return f"{texto} ({etiqueta})" if etiqueta else texto


def _periodo_respuesta(fecha_inicio, fecha_fin, periodo_etiqueta):
    periodo = {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin}
    if periodo_etiqueta:
        periodo["etiqueta"] = ETIQUETAS_PERIODO[periodo_etiqueta]
    return periodo


def _parametros_con_etiqueta(parametros, periodo_etiqueta):
    if periodo_etiqueta:
        parametros["periodo_etiqueta"] = periodo_etiqueta
    return parametros


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
    """Inserta la generación efectiva en `reporte` y devuelve id y fecha.

    El id_reporte lo consume RF35 (exportar a Excel) y RF34
    (exportar a PDF, Renato): con él y `parametros` se puede volver a
    consultar exactamente lo mismo que se mostró en pantalla.
    """
    cursor.execute(
        """
        INSERT INTO reporte (id_usuario, tipo_reporte, parametros)
        VALUES (%s, %s, %s)
        """,
        (id_usuario, tipo_reporte, json.dumps(parametros)),
    )
    cursor.execute(
        "SELECT id_reporte, DATE_FORMAT(fecha_generacion, '%d-%m-%Y %H:%i') AS fecha_generacion "
        "FROM reporte WHERE id_reporte = LAST_INSERT_ID()"
    )
    return cursor.fetchone()


@reportes_blueprint.route('/reportes/tareas-por-cliente', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def reporte_tareas_por_cliente():
    conexion = None
    try:
        id_cliente = request.args.get('id_cliente', '').strip()
        if id_cliente and (not id_cliente.isdecimal() or int(id_cliente) < 1):
            return jsonify({"error": "id_cliente debe ser un ID entero positivo"}), 400
        if not id_cliente:
            return jsonify({"error": "Debe indicar id_cliente."}), 400

        fecha_inicio, fecha_fin, error = _validar_periodo(request.args)
        if error:
            return jsonify({"error": error}), 400
        periodo_etiqueta, error = _etiqueta_periodo(request.args)
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
                "periodo": _periodo_respuesta(fecha_inicio, fecha_fin, periodo_etiqueta),
                "fecha_generacion": None,
                "tareas": tareas,
                "resumen_por_estado": resumen_por_estado,
            }

            if not tareas:
                respuesta["mensaje"] = MENSAJE_SIN_TAREAS
                return jsonify(respuesta), 200

            usuario_actual = obtener_usuario_actual()
            generacion = _registrar_generacion(
                cursor,
                usuario_actual["id_usuario"],
                "TAREAS_POR_CLIENTE",
                _parametros_con_etiqueta(
                    {"id_cliente": int(id_cliente), "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
                    periodo_etiqueta,
                ),
            )
            respuesta["id_reporte"] = generacion["id_reporte"]
            respuesta["fecha_generacion"] = generacion["fecha_generacion"]
            conexion.commit()

        return jsonify(respuesta), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al generar reporte de tareas por cliente")
        return jsonify({"error": "Ocurrió un error al generar el reporte."}), 500

    finally:
        if conexion:
            conexion.close()


def _a_datetime(valor):
    """Normaliza a `datetime` tanto el datetime que entrega mysql-connector
    como el texto ISO que devuelve SQLite en los tests (mismo criterio que
    `_fecha_a_date` en tareas_routes.py)."""
    if isinstance(valor, str):
        return datetime.strptime(valor[:19], "%Y-%m-%d %H:%M:%S")
    return valor


ACCIONES_DE_ASIGNACION = ("REASIGNACION", "REASIGNACION_MASIVA", "EDICION")


def _fechas_de_asignacion(cursor, completadas):
    """Fecha en que cada tarea completada pasó a su responsable final.

    CU-48 fija que el tiempo de resolución va «entre la asignación y el
    cierre». La tarea no guarda esa fecha: se toma de AUDITORIA el último
    cambio de responsable hacia el responsable que la cerró (RF16, RF19 o la
    edición de RF64), anterior al cierre. Si no hubo reasignación, la
    asignación es la creación de la tarea y la tarea no aparece aquí.
    """
    ids_tarea = [fila["id_tarea"] for fila in completadas if fila.get("id_tarea") is not None]
    if not ids_tarea:
        return {}

    marcadores = ", ".join(["%s"] * len(ids_tarea))
    marcadores_acciones = ", ".join(["%s"] * len(ACCIONES_DE_ASIGNACION))
    cursor.execute(
        f"""
        SELECT id_registro, datos_nuevos, fecha
        FROM auditoria
        WHERE tabla_afectada = 'tarea'
          AND accion IN ({marcadores_acciones})
          AND id_registro IN ({marcadores})
        """,
        (*ACCIONES_DE_ASIGNACION, *ids_tarea)
    )
    eventos = cursor.fetchall()

    por_tarea = {fila["id_tarea"]: fila for fila in completadas if fila.get("id_tarea") is not None}
    asignaciones = {}
    for evento in eventos:
        tarea = por_tarea.get(evento["id_registro"])
        if not tarea:
            continue
        esperado = f"id_tarea={tarea['id_tarea']}, id_responsable={tarea['id_responsable']}"
        fecha_evento = _a_datetime(evento["fecha"])
        if evento["datos_nuevos"] != esperado or fecha_evento > _a_datetime(tarea["fecha_finalizacion"]):
            continue
        anterior = asignaciones.get(tarea["id_tarea"])
        if anterior is None or fecha_evento > anterior:
            asignaciones[tarea["id_tarea"]] = fecha_evento

    return asignaciones


def _calcular_productividad(cursor, fecha_inicio, fecha_fin, id_area=None):
    """Consulta compartida de RF39, reutilizada tal cual por la exportación a
    Excel de RF35: por cada usuario activo (filtrable por área), tareas
    completadas dentro del período, tiempo promedio de resolución (desde la
    asignación hasta el cierre) y carga vigente. Devuelve la lista ya
    ordenada por tareas completadas."""
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
            SELECT id_tarea, id_responsable, fecha_creacion, fecha_finalizacion
            FROM tarea
            WHERE estado = 'COMPLETADA'
              AND id_responsable IN ({marcadores})
              AND fecha_finalizacion >= %s
              AND fecha_finalizacion < DATE_ADD(%s, INTERVAL 1 DAY)
            """,
            (*ids_usuario, fecha_inicio, fecha_fin)
        )
        completadas = cursor.fetchall()
        asignaciones = _fechas_de_asignacion(cursor, completadas)

        for fila in completadas:
            datos = acumulado[fila["id_responsable"]]
            datos["completadas"] += 1
            inicio = asignaciones.get(fila.get("id_tarea")) or _a_datetime(fila["fecha_creacion"])
            duracion = _a_datetime(fila["fecha_finalizacion"]) - inicio
            datos["segundos_totales"] += max(duracion.total_seconds(), 0)

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
    return resultado


@reportes_blueprint.route('/reportes/productividad', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def reporte_productividad_por_usuario():
    """RF39 — Visualizando la Productividad por Usuario.

    Por cada usuario activo (filtrable por área): tareas completadas dentro
    del período, tiempo promedio de resolución entre la asignación y el
    cierre (CU-48; ver _fechas_de_asignacion) y carga vigente (PENDIENTE o
    EN_PROCESO, sin filtrar por período: es una fotografía del momento).
    Si nadie completó tareas en el período se informa la excepción de CU-48
    y, como en RF31, no se registra la generación.
    """
    conexion = None
    try:
        fecha_inicio, fecha_fin, error = _validar_periodo(request.args)
        if error:
            return jsonify({"error": error}), 400
        periodo_etiqueta, error = _etiqueta_periodo(request.args)
        if error:
            return jsonify({"error": error}), 400

        id_area = request.args.get('id_area', '').strip()
        if id_area and (not id_area.isdecimal() or int(id_area) < 1):
            return jsonify({"error": "id_area debe ser un ID entero positivo"}), 400

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión con MySQL."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            if id_area:
                cursor.execute("SELECT id_area FROM area WHERE id_area = %s", (id_area,))
                if not cursor.fetchone():
                    return jsonify({"error": "Área inexistente."}), 404

            resultado = _calcular_productividad(cursor, fecha_inicio, fecha_fin, id_area)

            respuesta = {
                "periodo": _periodo_respuesta(fecha_inicio, fecha_fin, periodo_etiqueta),
                "usuarios": resultado,
            }

            if not resultado:
                respuesta["mensaje"] = "No hay usuarios activos para los criterios seleccionados"
                return jsonify(respuesta), 200

            if not any(fila["tareas_completadas"] for fila in resultado):
                respuesta["mensaje"] = MENSAJE_SIN_COMPLETADAS
                return jsonify(respuesta), 200

            usuario_actual = obtener_usuario_actual()
            generacion = _registrar_generacion(
                cursor,
                usuario_actual["id_usuario"],
                "PRODUCTIVIDAD_POR_USUARIO",
                _parametros_con_etiqueta(
                    {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin, "id_area": id_area or None},
                    periodo_etiqueta,
                ),
            )
            respuesta["id_reporte"] = generacion["id_reporte"]
            respuesta["fecha_generacion"] = generacion["fecha_generacion"]
            conexion.commit()

        return jsonify(respuesta), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al generar reporte de productividad por usuario")
        return jsonify({"error": "Ocurrió un error al generar el reporte."}), 500

    finally:
        if conexion:
            conexion.close()


def _resumen_actividad_por_area(cursor, fecha_inicio, fecha_fin):
    """Resume clientes asignados y usuarios activos creados en el período,
    junto con las tareas creadas, por cada área registrada."""
    cursor.execute("SELECT id_area, nombre_area FROM area ORDER BY nombre_area")
    areas = cursor.fetchall()
    if not areas:
        return []

    cursor.execute(
        "SELECT id_area, COUNT(DISTINCT id_cliente) AS total "
        "FROM cliente_area "
        "WHERE fecha_asignacion >= %s "
        "AND fecha_asignacion < DATE_ADD(%s, INTERVAL 1 DAY) GROUP BY id_area",
        (fecha_inicio, fecha_fin),
    )
    clientes_por_area = {fila["id_area"]: fila["total"] for fila in cursor.fetchall()}

    cursor.execute(
        """
        SELECT id_area, COUNT(*) AS total
        FROM tarea
        WHERE fecha_creacion >= %s
          AND fecha_creacion < DATE_ADD(%s, INTERVAL 1 DAY)
        GROUP BY id_area
        """,
        (fecha_inicio, fecha_fin),
    )
    tareas_por_area = {fila["id_area"]: fila["total"] for fila in cursor.fetchall()}

    cursor.execute(
        "SELECT id_area, COUNT(*) AS total FROM usuario "
        "WHERE estado = 'ACTIVO' AND fecha_creacion >= %s "
        "AND fecha_creacion < DATE_ADD(%s, INTERVAL 1 DAY) GROUP BY id_area",
        (fecha_inicio, fecha_fin),
    )
    usuarios_por_area = {fila["id_area"]: fila["total"] for fila in cursor.fetchall()}

    return [
        {
            "id_area": area["id_area"],
            "nombre_area": area["nombre_area"],
            "clientes": clientes_por_area.get(area["id_area"], 0),
            "tareas": tareas_por_area.get(area["id_area"], 0),
            "usuarios": usuarios_por_area.get(area["id_area"], 0),
        }
        for area in areas
    ]


def _comparacion_areas(areas):
    """Compara JURIDICA y CONTABLE cuando ambas están configuradas."""
    por_nombre = {area["nombre_area"].strip().upper(): area for area in areas}
    juridica = por_nombre.get("JURIDICA")
    contable = por_nombre.get("CONTABLE")
    if not juridica or not contable:
        return {"disponible": False}

    metricas = ("clientes", "tareas", "usuarios")
    return {
        "disponible": True,
        "juridica": juridica,
        "contable": contable,
        "diferencias": {
            metrica: juridica[metrica] - contable[metrica]
            for metrica in metricas
        },
    }


@reportes_blueprint.route('/reportes/actividad-por-area', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def reporte_actividad_por_area():
    """RF33 — Reportando por área de trabajo.

    Cuenta clientes asignados por fecha_asignacion, tareas por fecha_creacion
    y usuarios activos por fecha_creacion, dentro del período elegido.
    """
    conexion = None
    try:
        fecha_inicio, fecha_fin, error = _validar_periodo(request.args)
        if error:
            return jsonify({"error": error}), 400
        periodo_etiqueta, error = _etiqueta_periodo(request.args)
        if error:
            return jsonify({"error": error}), 400

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión con MySQL."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            areas = _resumen_actividad_por_area(cursor, fecha_inicio, fecha_fin)
            usuario_actual = obtener_usuario_actual()
            parametros = _parametros_con_etiqueta(
                {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
                periodo_etiqueta,
            )
            generacion = _registrar_generacion(
                cursor, usuario_actual["id_usuario"], "ACTIVIDAD_POR_AREA", parametros
            )
            conexion.commit()

        return jsonify({
            "periodo": _periodo_respuesta(fecha_inicio, fecha_fin, periodo_etiqueta),
            "areas": areas,
            "comparacion": _comparacion_areas(areas),
            "id_reporte": generacion["id_reporte"],
            "fecha_generacion": generacion["fecha_generacion"],
        }), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al generar reporte de actividad por área")
        return jsonify({"error": "Ocurrió un error al generar el reporte."}), 500

    finally:
        if conexion:
            conexion.close()


@reportes_blueprint.route('/reportes/distribucion-por-area', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def distribucion_actual_por_area():
    """RF45 — Distribución actual de clientes y tareas por área.

    Los porcentajes de clientes usan como denominador las relaciones únicas
    cliente-área; un mismo cliente puede participar en más de un área.
    """
    conexion = None
    try:
        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión con MySQL."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT id_area, nombre_area FROM area ORDER BY nombre_area")
            areas = cursor.fetchall()

            cursor.execute(
                "SELECT id_area, COUNT(DISTINCT id_cliente) AS total "
                "FROM cliente_area GROUP BY id_area"
            )
            clientes_por_area = {
                fila["id_area"]: int(fila["total"] or 0)
                for fila in cursor.fetchall()
            }

            cursor.execute(
                "SELECT COUNT(DISTINCT id_cliente) AS total FROM cliente_area"
            )
            total_clientes = int((cursor.fetchone() or {}).get("total", 0) or 0)

            cursor.execute(
                "SELECT id_area, COUNT(*) AS total FROM tarea GROUP BY id_area"
            )
            tareas_por_area = {
                fila["id_area"]: int(fila["total"] or 0)
                for fila in cursor.fetchall()
            }

            total_tareas = sum(tareas_por_area.values())
            total_asignaciones_cliente_area = sum(clientes_por_area.values())
            distribucion = []

            for area in areas:
                cantidad_clientes = clientes_por_area.get(area["id_area"], 0)
                cantidad_tareas = tareas_por_area.get(area["id_area"], 0)
                distribucion.append({
                    "id_area": area["id_area"],
                    "nombre_area": area["nombre_area"],
                    "clientes": cantidad_clientes,
                    "porcentaje_clientes": round(
                        cantidad_clientes * 100.0 / total_asignaciones_cliente_area,
                        1,
                    ) if total_asignaciones_cliente_area else 0.0,
                    "tareas": cantidad_tareas,
                    "porcentaje_tareas": round(
                        cantidad_tareas * 100.0 / total_tareas, 1
                    ) if total_tareas else 0.0,
                })

        return jsonify({
            "areas": distribucion,
            "total_clientes": total_clientes,
            "total_asignaciones_cliente_area": total_asignaciones_cliente_area,
            "total_tareas": total_tareas,
        }), 200

    except Exception:
        logger.exception("Error al calcular la distribución actual por área")
        return jsonify({"error": "Ocurrió un error al calcular la distribución por área."}), 500

    finally:
        if conexion:
            conexion.close()


@reportes_blueprint.route('/reportes/carga-por-usuario', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def carga_por_usuario():
    """RF44 — Carga de trabajo por usuario.

    Muestra el desglose real de tareas por estado para cada usuario activo,
    con opción de limitar la comparación a un área concreta. La consulta se
    basa en la base actual y no inventa ponderaciones ni fórmulas arbitrarias.
    """
    conexion = None
    try:
        id_area = (request.args.get('id_area') or '').strip()
        if id_area and (not id_area.isdecimal() or int(id_area) < 1):
            return jsonify({"error": "id_area debe ser un ID entero positivo"}), 400

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión con MySQL."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            consulta_usuarios = """
                SELECT u.id_usuario, u.nombres, u.id_area, a.nombre_area, u.estado
                FROM usuario u
                LEFT JOIN area a ON a.id_area = u.id_area
                WHERE u.estado = 'ACTIVO'
            """
            parametros = []
            if id_area:
                consulta_usuarios += " AND u.id_area = %s"
                parametros.append(int(id_area))
            consulta_usuarios += " ORDER BY u.id_area, u.nombres"
            cursor.execute(consulta_usuarios, tuple(parametros))
            usuarios = [
                usuario for usuario in cursor.fetchall()
                if usuario.get("estado") == "ACTIVO"
            ]

            if not usuarios:
                return jsonify({
                    "usuarios": [],
                    "mensaje": "No hay usuarios activos para los criterios seleccionados",
                }), 200

            ids_usuario = [usuario["id_usuario"] for usuario in usuarios]
            marcadores = ", ".join(["%s"] * len(ids_usuario))
            consulta_tareas = f"""
                SELECT u.id_usuario,
                       SUM(CASE WHEN t.estado = 'PENDIENTE' THEN 1 ELSE 0 END) AS PENDIENTE,
                       SUM(CASE WHEN t.estado = 'EN_PROCESO' THEN 1 ELSE 0 END) AS EN_PROCESO,
                       SUM(CASE WHEN t.estado = 'EN_REVISION' THEN 1 ELSE 0 END) AS EN_REVISION,
                       SUM(CASE WHEN t.estado = 'COMPLETADA' THEN 1 ELSE 0 END) AS COMPLETADA,
                       SUM(CASE WHEN t.estado = 'CANCELADA' THEN 1 ELSE 0 END) AS CANCELADA
                FROM usuario u
                LEFT JOIN tarea t ON t.id_responsable = u.id_usuario
                WHERE u.id_usuario IN ({marcadores})
                GROUP BY u.id_usuario
            """
            cursor.execute(consulta_tareas, tuple(ids_usuario))

            conteos = {}
            for fila in cursor.fetchall():
                conteos[fila["id_usuario"]] = {
                    "PENDIENTE": int(fila.get("PENDIENTE") or 0),
                    "EN_PROCESO": int(fila.get("EN_PROCESO") or 0),
                    "EN_REVISION": int(fila.get("EN_REVISION") or 0),
                    "COMPLETADA": int(fila.get("COMPLETADA") or 0),
                    "CANCELADA": int(fila.get("CANCELADA") or 0),
                }

            carga = []
            for usuario in usuarios:
                por_estado = conteos.get(
                    usuario["id_usuario"],
                    {
                        "PENDIENTE": 0,
                        "EN_PROCESO": 0,
                        "EN_REVISION": 0,
                        "COMPLETADA": 0,
                        "CANCELADA": 0,
                    },
                )
                total = sum(por_estado.values())
                carga.append({
                    "id_usuario": usuario["id_usuario"],
                    "usuario": usuario["nombres"],
                    "id_area": usuario["id_area"],
                    "nombre_area": usuario.get("nombre_area") or "Sin área",
                    "estado": usuario["estado"],
                    "por_estado": por_estado,
                    "total_tareas": total,
                })

            respuesta = {"usuarios": carga}
            if id_area:
                respuesta["area"] = {
                    "id_area": int(id_area),
                    "nombre_area": (usuarios[0] or {}).get("nombre_area") or "Área seleccionada",
                }

            return jsonify(respuesta), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al calcular la carga de trabajo por usuario")
        return jsonify({"error": "Ocurrió un error al calcular la carga de trabajo por usuario."}), 500

    finally:
        if conexion:
            conexion.close()


@reportes_blueprint.route('/reportes/tareas-por-responsable', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def reporte_tareas_por_responsable():
    conexion = None
    try:
        id_responsable = request.args.get('id_responsable', '').strip()
        if id_responsable and (not id_responsable.isdecimal() or int(id_responsable) < 1):
            return jsonify({"error": "id_responsable debe ser un ID entero positivo"}), 400
        if not id_responsable:
            return jsonify({"error": "Debe indicar id_responsable."}), 400

        fecha_inicio, fecha_fin, error = _validar_periodo(request.args)
        if error:
            return jsonify({"error": error}), 400
        periodo_etiqueta, error = _etiqueta_periodo(request.args)
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
                "periodo": _periodo_respuesta(fecha_inicio, fecha_fin, periodo_etiqueta),
                "fecha_generacion": None,
                "tareas": tareas,
                "resumen_por_estado": resumen_por_estado,
            }

            if not tareas:
                respuesta["mensaje"] = MENSAJE_SIN_TAREAS
                return jsonify(respuesta), 200

            usuario_actual = obtener_usuario_actual()
            generacion = _registrar_generacion(
                cursor,
                usuario_actual["id_usuario"],
                "TAREAS_POR_RESPONSABLE",
                _parametros_con_etiqueta(
                    {"id_responsable": int(id_responsable), "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
                    periodo_etiqueta,
                ),
            )
            respuesta["id_reporte"] = generacion["id_reporte"]
            respuesta["fecha_generacion"] = generacion["fecha_generacion"]
            conexion.commit()

        return jsonify(respuesta), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al generar reporte de tareas por responsable")
        return jsonify({"error": "Ocurrió un error al generar el reporte."}), 500

    finally:
        if conexion:
            conexion.close()


# ==========================================================================
# RF40 — Historiando Consolidadamente las Actividades.
# Reporte del período sobre AUDITORIA (backend/utils/auditoria.py, RF56):
# consolida la actividad de todos los módulos, filtrable por módulo (tipo de
# actividad), usuario y rango de fechas, y se exporta a PDF/Excel con el
# mismo mecanismo que el resto de los reportes (tabla REPORTE + id_reporte).
# ==========================================================================

LIMITE_HISTORIAL_CONSOLIDADO = 5000
MENSAJE_SIN_ACTIVIDADES = "No se registran actividades para los criterios seleccionados"


def _filtros_historial_consolidado(parametros):
    """Traduce los parámetros guardados/recibidos a los de consultar_auditoria.

    Devuelve (kwargs, error)."""
    kwargs = {
        "fecha_inicio": parametros.get("fecha_inicio"),
        "fecha_fin": parametros.get("fecha_fin"),
    }

    modulo = (parametros.get("modulo") or "").strip()
    if modulo:
        if modulo not in modulos_disponibles():
            return None, "El módulo indicado no existe."
        kwargs["tablas"] = tablas_de_modulo(modulo)

    id_usuario = parametros.get("id_usuario")
    if id_usuario not in (None, ""):
        if not str(id_usuario).isdigit():
            return None, "El usuario indicado no es válido."
        kwargs["id_usuario"] = int(id_usuario)

    return kwargs, None


def _consultar_historial_consolidado(cursor, parametros):
    """Devuelve (eventos, total, resumen_por_modulo, resumen_por_accion)."""
    kwargs, _ = _filtros_historial_consolidado(parametros)
    eventos, total = consultar_auditoria(cursor, limite=LIMITE_HISTORIAL_CONSOLIDADO, **kwargs)

    resumen_por_modulo = {}
    resumen_por_accion = {}
    for evento in eventos:
        resumen_por_modulo[evento["modulo"]] = resumen_por_modulo.get(evento["modulo"], 0) + 1
        resumen_por_accion[evento["accion"]] = resumen_por_accion.get(evento["accion"], 0) + 1

    return eventos, total, resumen_por_modulo, resumen_por_accion


@reportes_blueprint.route('/reportes/historial-consolidado', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def reporte_historial_consolidado():
    conexion = None
    try:
        fecha_inicio, fecha_fin, error = _validar_periodo(request.args)
        if error:
            return jsonify({"error": error}), 400

        parametros = {
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "modulo": (request.args.get("modulo") or "").strip() or None,
            "id_usuario": (request.args.get("id_usuario") or "").strip() or None,
        }
        _, error = _filtros_historial_consolidado(parametros)
        if error:
            return jsonify({"error": error}), 400
        if parametros["id_usuario"]:
            parametros["id_usuario"] = int(parametros["id_usuario"])

        usuario_sesion = obtener_usuario_actual()

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión con MySQL."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            usuario_filtrado = None
            if parametros["id_usuario"]:
                cursor.execute(
                    "SELECT id_usuario, nombres FROM usuario WHERE id_usuario = %s",
                    (parametros["id_usuario"],),
                )
                usuario_filtrado = cursor.fetchone()
                if not usuario_filtrado:
                    return jsonify({"error": "Usuario inexistente."}), 404

            eventos, total, resumen_por_modulo, resumen_por_accion = _consultar_historial_consolidado(
                cursor, parametros
            )

            respuesta = {
                "periodo": {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
                "filtros": {"modulo": parametros["modulo"], "usuario": usuario_filtrado},
                "total": total,
                "truncado": total > len(eventos),
                "eventos": eventos,
                "resumen_por_modulo": resumen_por_modulo,
                "resumen_por_accion": resumen_por_accion,
                "id_reporte": None,
                "fecha_generacion": None,
            }

            if not eventos:
                respuesta["mensaje"] = MENSAJE_SIN_ACTIVIDADES
                return jsonify(respuesta), 200

            generado = _registrar_generacion(
                cursor, usuario_sesion["id_usuario"], "HISTORIAL_CONSOLIDADO", parametros
            )
            conexion.commit()

            respuesta["id_reporte"] = generado["id_reporte"]
            respuesta["fecha_generacion"] = generado["fecha_generacion"]
            return jsonify(respuesta), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al generar el historial consolidado")
        return jsonify({"error": "Ocurrió un error al generar el historial consolidado."}), 500

    finally:
        if conexion:
            conexion.close()


_CARACTERES_INVALIDOS_ARCHIVO = '\\/:*?"<>|'


def _nombre_archivo_seguro(texto):
    """Deja `texto` seguro para usarlo en un nombre de archivo en cualquier
    sistema operativo, reemplazando espacios y caracteres reservados."""
    limpio = "".join(
        "_" if caracter in _CARACTERES_INVALIDOS_ARCHIVO or caracter.isspace() else caracter
        for caracter in str(texto)
    )
    return limpio.strip("_") or "reporte"


def _datos_para_exportar(cursor, tipo_reporte, parametros):
    """Capa de consulta compartida para exportar (RF35, Elías; ver
    equipo.json → coordinación). Vuelve a consultar con los parámetros
    guardados en `reporte` —igual que el PDF de RF34— en vez de
    convertir el HTML ya renderizado, así ambos formatos no pueden divergir.

    Devuelve (nombre_archivo, encabezados, filas) o None si el tipo de
    reporte guardado no tiene un formato de exportación definido.
    """
    fecha_inicio = parametros.get("fecha_inicio")
    fecha_fin = parametros.get("fecha_fin")

    if tipo_reporte in ("TAREAS_POR_CLIENTE", "TAREAS_POR_RESPONSABLE"):
        id_cliente = parametros.get("id_cliente")
        id_responsable = parametros.get("id_responsable")

        tareas, _ = _consultar_tareas_periodo(
            cursor, fecha_inicio, fecha_fin,
            id_cliente=id_cliente, id_responsable=id_responsable,
        )

        encabezados = [
            "Título", "Cliente", "Responsable", "Estado", "Prioridad",
            "Fecha de creación", "Fecha de vencimiento",
        ]
        filas = [
            [
                tarea["titulo"], tarea["cliente"], tarea["responsable"],
                tarea["estado"], tarea["prioridad"],
                tarea["fecha_creacion"], tarea["fecha_vencimiento"] or "",
            ]
            for tarea in tareas
        ]

        if tipo_reporte == "TAREAS_POR_CLIENTE":
            cursor.execute("SELECT razon_social FROM cliente WHERE id_cliente = %s", (id_cliente,))
            entidad = cursor.fetchone()
            etiqueta = entidad["razon_social"] if entidad else str(id_cliente)
            base = f"reporte_tareas_por_cliente_{etiqueta}"
        else:
            cursor.execute("SELECT nombres FROM usuario WHERE id_usuario = %s", (id_responsable,))
            entidad = cursor.fetchone()
            etiqueta = entidad["nombres"] if entidad else str(id_responsable)
            base = f"reporte_tareas_por_responsable_{etiqueta}"

        nombre = f"{_nombre_archivo_seguro(base)}_{fecha_inicio}_a_{fecha_fin}.xlsx"
        return nombre, encabezados, filas

    if tipo_reporte == "PRODUCTIVIDAD_POR_USUARIO":
        id_area = parametros.get("id_area")
        resultado = _calcular_productividad(cursor, fecha_inicio, fecha_fin, id_area)

        encabezados = [
            "Usuario", "Tareas completadas",
            "Tiempo promedio de resolución (horas)", "Carga vigente",
        ]
        filas = [
            [
                fila["usuario"], fila["tareas_completadas"],
                fila["tiempo_promedio_resolucion_horas"] if fila["tiempo_promedio_resolucion_horas"] is not None else "",
                fila["carga_vigente"],
            ]
            for fila in resultado
        ]

        nombre = f"reporte_productividad_area_{id_area or 'todas'}_{fecha_inicio}_a_{fecha_fin}.xlsx"
        return nombre, encabezados, filas

    if tipo_reporte == "ACTIVIDAD_POR_AREA":
        areas = _resumen_actividad_por_area(cursor, fecha_inicio, fecha_fin)
        encabezados = [
            "Área", "Clientes asignados en el período", "Tareas del período",
            "Usuarios activos creados en el período",
        ]
        filas = [
            [area["nombre_area"], area["clientes"], area["tareas"], area["usuarios"]]
            for area in areas
        ]
        nombre = f"reporte_actividad_por_area_{fecha_inicio}_a_{fecha_fin}.xlsx"
        return nombre, encabezados, filas

    if tipo_reporte == "HISTORIAL_CONSOLIDADO":
        eventos, _, _, _ = _consultar_historial_consolidado(cursor, parametros)

        encabezados = ["Fecha y hora", "Usuario", "Módulo", "Acción", "Registro", "Antes", "Después"]
        filas = [
            [
                evento["fecha"], evento["usuario"] or "", evento["modulo"], evento["accion"],
                f"{evento['tabla_afectada']} #{evento['id_registro']}" if evento["id_registro"] else evento["tabla_afectada"],
                evento["datos_anteriores"] or "", evento["datos_nuevos"] or "",
            ]
            for evento in eventos
        ]

        modulo = parametros.get("modulo") or "todos_los_modulos"
        nombre = f"{_nombre_archivo_seguro('historial_consolidado_' + modulo)}_{fecha_inicio}_a_{fecha_fin}.xlsx"
        return nombre, encabezados, filas

    return None


def _filtros_para_exportar(cursor, tipo_reporte, parametros):
    """Filtros del reporte guardado, en texto, para el encabezado del PDF y
    la hoja «Parámetros» del Excel: el archivo debe decir por sí mismo qué
    consulta representa, no solo su nombre."""
    filtros = []

    if tipo_reporte == "TAREAS_POR_CLIENTE":
        cursor.execute("SELECT razon_social FROM cliente WHERE id_cliente = %s", (parametros.get("id_cliente"),))
        entidad = cursor.fetchone()
        filtros.append(("Cliente", entidad["razon_social"] if entidad else str(parametros.get("id_cliente"))))
    elif tipo_reporte == "TAREAS_POR_RESPONSABLE":
        cursor.execute("SELECT nombres FROM usuario WHERE id_usuario = %s", (parametros.get("id_responsable"),))
        entidad = cursor.fetchone()
        filtros.append(("Usuario responsable", entidad["nombres"] if entidad else str(parametros.get("id_responsable"))))
    elif tipo_reporte == "PRODUCTIVIDAD_POR_USUARIO":
        area = "Todas las áreas"
        if parametros.get("id_area"):
            cursor.execute("SELECT nombre_area FROM area WHERE id_area = %s", (parametros.get("id_area"),))
            entidad = cursor.fetchone()
            area = entidad["nombre_area"] if entidad else str(parametros.get("id_area"))
        filtros.append(("Área", area))
    elif tipo_reporte == "ACTIVIDAD_POR_AREA":
        filtros.append(("Áreas", "Todas las áreas registradas"))
    elif tipo_reporte == "HISTORIAL_CONSOLIDADO":
        filtros.append(("Módulo", parametros.get("modulo") or "Todos los módulos"))
        usuario = "Todos los usuarios"
        if parametros.get("id_usuario"):
            cursor.execute("SELECT nombres FROM usuario WHERE id_usuario = %s", (parametros.get("id_usuario"),))
            entidad = cursor.fetchone()
            usuario = entidad["nombres"] if entidad else str(parametros.get("id_usuario"))
        filtros.append(("Usuario", usuario))

    return filtros


def _texto_fecha_generacion(valor):
    if isinstance(valor, datetime):
        return f"{valor:%d-%m-%Y %H:%M}"
    return str(valor) if valor else None


@reportes_blueprint.route('/reportes/<int:id_reporte>/pdf', methods=['GET'], defaults={'formato': 'pdf'})
@reportes_blueprint.route('/reportes/<int:id_reporte>/excel', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def exportar_reporte_excel(id_reporte, formato="excel"):
    """RF35 — Exportando Reportes en Formato Excel.

    Recibe el id_reporte que devolvió la generación en pantalla (RF31, RF32,
    RF39) y arma el .xlsx con _datos_para_exportar: una fila por elemento del
    reporte y los mismos encabezados que se ven en pantalla.
    """
    conexion = None
    try:
        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión con MySQL."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT id_reporte, tipo_reporte, parametros, fecha_generacion FROM reporte WHERE id_reporte = %s",
                (id_reporte,),
            )
            reporte = cursor.fetchone()
            if not reporte:
                return jsonify({"error": "Reporte inexistente."}), 404

            parametros = reporte["parametros"]
            if isinstance(parametros, str):
                parametros = json.loads(parametros)

            resultado = _datos_para_exportar(cursor, reporte["tipo_reporte"], parametros)
            if resultado is None:
                return jsonify({"error": "Este tipo de reporte no se puede exportar a Excel."}), 400

            nombre_archivo, encabezados, filas = resultado
            filtros = _filtros_para_exportar(cursor, reporte["tipo_reporte"], parametros)

        titulo = {
            "TAREAS_POR_CLIENTE": "Tareas por cliente",
            "TAREAS_POR_RESPONSABLE": "Tareas por usuario responsable",
            "PRODUCTIVIDAD_POR_USUARIO": "Productividad por usuario",
            "ACTIVIDAD_POR_AREA": "Actividad por área de trabajo",
            "HISTORIAL_CONSOLIDADO": "Historial consolidado de actividades",
        }.get(reporte["tipo_reporte"], "Reporte")
        fecha_exportacion = f"{datetime.now():%d-%m-%Y %H:%M}"
        fecha_generacion = _texto_fecha_generacion(reporte.get("fecha_generacion")) or fecha_exportacion

        if formato == "pdf":
            buffer = io.BytesIO()
            estilos = getSampleStyleSheet()
            estilos["BodyText"].fontSize = 8
            estilos["BodyText"].leading = 10
            documento = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                                          rightMargin=24, leftMargin=24,
                                          topMargin=24, bottomMargin=24, title=titulo)
            contenido = [
                Paragraph(escape(titulo), estilos["Title"]),
                Paragraph(escape(f"Período: {_texto_periodo(parametros)}"), estilos["Normal"]),
                *[Paragraph(escape(f"{etiqueta}: {valor}"), estilos["Normal"]) for etiqueta, valor in filtros],
                Paragraph(escape(f"Fecha de generación: {fecha_generacion} · Exportado: {fecha_exportacion}"),
                          estilos["Normal"]),
                Spacer(1, 12),
            ]
            if reporte["tipo_reporte"].startswith("TAREAS_"):
                resumen = {}
                for fila in filas:
                    resumen[fila[3]] = resumen.get(fila[3], 0) + 1
                contenido.append(Paragraph(escape("Resumen por estado: " + ", ".join(
                    f"{estado}: {total}" for estado, total in resumen.items()
                )), estilos["Normal"]))
            if reporte["tipo_reporte"] == "HISTORIAL_CONSOLIDADO":
                resumen = {}
                for fila in filas:
                    resumen[fila[2]] = resumen.get(fila[2], 0) + 1
                contenido.append(Paragraph(escape("Actividades por módulo: " + ", ".join(
                    f"{modulo}: {total}" for modulo, total in sorted(resumen.items())
                )), estilos["Normal"]))
            datos = [[Paragraph(escape(str(valor)), estilos["BodyText"])
                      for valor in fila] for fila in [encabezados, *filas]]
            tabla = LongTable(datos, colWidths=[documento.width / len(encabezados)] * len(encabezados),
                              repeatRows=1, splitInRow=1)
            tabla.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            contenido.append(tabla)
            if not filas:
                sin_datos = (MENSAJE_SIN_ACTIVIDADES if reporte["tipo_reporte"] == "HISTORIAL_CONSOLIDADO"
                             else MENSAJE_SIN_TAREAS)
                contenido.append(Paragraph(sin_datos, estilos["Normal"]))
            documento.build(contenido)
            buffer.seek(0)
            return send_file(buffer, mimetype="application/pdf", as_attachment=True,
                             download_name=nombre_archivo.rsplit(".", 1)[0] + ".pdf")

        libro = Workbook()
        hoja = libro.active
        hoja.title = "Reporte"
        hoja.append(encabezados)
        for fila in filas:
            hoja.append(fila)
            # Los textos del usuario son datos, nunca fórmulas ejecutables.
            for celda in hoja[hoja.max_row]:
                if celda.data_type == "f":
                    celda.data_type = "s"

        # Segunda hoja con los parámetros del reporte: la primera conserva una
        # fila por elemento y los encabezados (criterio de RF35), y esta deja
        # el período y los filtros dentro del propio archivo (RF38).
        hoja_parametros = libro.create_sheet("Parámetros")
        for fila in [
            ("Reporte", titulo),
            ("Período", _texto_periodo(parametros)),
            *filtros,
            ("Fecha de generación", fecha_generacion),
            ("Fecha de exportación", fecha_exportacion),
            ("Identificador del reporte", reporte["id_reporte"]),
        ]:
            hoja_parametros.append(fila)
            for celda in hoja_parametros[hoja_parametros.max_row]:
                if celda.data_type == "f":
                    celda.data_type = "s"

        buffer = io.BytesIO()
        libro.save(buffer)
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=nombre_archivo,
        )

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al exportar reporte a Excel")
        return jsonify({"error": "Ocurrió un error al exportar el reporte."}), 500

    finally:
        if conexion:
            conexion.close()
