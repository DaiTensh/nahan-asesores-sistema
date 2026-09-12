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
            generacion = _registrar_generacion(
                cursor,
                usuario_actual["id_usuario"],
                "TAREAS_POR_CLIENTE",
                {"id_cliente": int(id_cliente), "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
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


def _calcular_productividad(cursor, fecha_inicio, fecha_fin, id_area=None):
    """Consulta compartida de RF39, reutilizada tal cual por la exportación a
    Excel de RF35: por cada usuario activo (filtrable por área), tareas
    completadas dentro del período, tiempo promedio de resolución y carga
    vigente. Devuelve la lista ya ordenada por tareas completadas."""
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
    return resultado


@reportes_blueprint.route('/reportes/productividad', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def reporte_productividad_por_usuario():
    """RF39 — Visualizando la Productividad por Usuario.

    Por cada usuario activo (filtrable por área): tareas completadas dentro
    del período, tiempo promedio de resolución (entre fecha_creacion y
    fecha_finalizacion; el modelo no guarda una fecha de asignación explícita).
    Este criterio requiere contraste con CU-48, no disponible en el repositorio.
    También informa carga vigente (PENDIENTE o
    EN_PROCESO, sin filtrar por período: es una fotografía del momento).
    """
    conexion = None
    try:
        fecha_inicio, fecha_fin, error = _validar_periodo(request.args)
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
                "periodo": {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
                "usuarios": resultado,
            }

            if not resultado:
                respuesta["mensaje"] = "No hay usuarios activos para los criterios seleccionados"
                return jsonify(respuesta), 200

            usuario_actual = obtener_usuario_actual()
            generacion = _registrar_generacion(
                cursor,
                usuario_actual["id_usuario"],
                "PRODUCTIVIDAD_POR_USUARIO",
                {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin, "id_area": id_area or None},
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
            generacion = _registrar_generacion(
                cursor,
                usuario_actual["id_usuario"],
                "TAREAS_POR_RESPONSABLE",
                {"id_responsable": int(id_responsable), "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
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

    return None


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
                "SELECT id_reporte, tipo_reporte, parametros FROM reporte WHERE id_reporte = %s",
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

        if formato == "pdf":
            buffer = io.BytesIO()
            estilos = getSampleStyleSheet()
            estilos["BodyText"].fontSize = 8
            estilos["BodyText"].leading = 10
            titulo = {
                "TAREAS_POR_CLIENTE": "Tareas por cliente",
                "TAREAS_POR_RESPONSABLE": "Tareas por usuario responsable",
                "PRODUCTIVIDAD_POR_USUARIO": "Productividad por usuario",
            }[reporte["tipo_reporte"]]
            documento = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                                          rightMargin=24, leftMargin=24,
                                          topMargin=24, bottomMargin=24, title=titulo)
            contenido = [
                Paragraph(escape(titulo), estilos["Title"]),
                Paragraph(escape(f"Período: {parametros['fecha_inicio']} a {parametros['fecha_fin']}"), estilos["Normal"]),
                Paragraph(f"Fecha de generación: {datetime.now():%d-%m-%Y %H:%M}", estilos["Normal"]),
                Spacer(1, 12),
            ]
            if reporte["tipo_reporte"].startswith("TAREAS_"):
                resumen = {}
                for fila in filas:
                    resumen[fila[3]] = resumen.get(fila[3], 0) + 1
                contenido.append(Paragraph(escape("Resumen por estado: " + ", ".join(
                    f"{estado}: {total}" for estado, total in resumen.items()
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
                contenido.append(Paragraph(MENSAJE_SIN_TAREAS, estilos["Normal"]))
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
