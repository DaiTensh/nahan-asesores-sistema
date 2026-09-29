import calendar
import logging
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from backend.config.db import get_connection
from backend.routes.notificaciones_routes import crear_notificacion
from backend.utils.auditoria import registrar_auditoria
from backend.utils.auth import ROL_ADMINISTRADOR, login_required, obtener_usuario_actual, roles_required

tareas_bp = Blueprint("tareas", __name__)
logger = logging.getLogger(__name__)

ESTADOS_FINALES = {"COMPLETADA", "CANCELADA"}
ESTADOS_VALIDOS = ["PENDIENTE", "EN_PROCESO", "EN_REVISION", "COMPLETADA", "CANCELADA"]
ESTADOS_PENDIENTE = ("PENDIENTE", "EN_PROCESO", "EN_REVISION")


def _validar_rango_tareas(args):
    """Valida un rango opcional de fechas para RF36."""
    fecha_inicio = (args.get("fecha_inicio") or "").strip()
    fecha_fin = (args.get("fecha_fin") or "").strip()

    if not fecha_inicio and not fecha_fin:
        return None, None, None

    if not fecha_inicio or not fecha_fin:
        return None, None, "Debe indicar fecha_inicio y fecha_fin (formato AAAA-MM-DD)."

    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
        fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
    except ValueError:
        return None, None, "Las fechas deben tener el formato AAAA-MM-DD."

    if fecha_inicio_dt > fecha_fin_dt:
        return None, None, "fecha_inicio no puede ser posterior a fecha_fin."

    return fecha_inicio_dt.isoformat(), fecha_fin_dt.isoformat(), None


def _rango_periodo_anterior(fecha_inicio, fecha_fin):
    """Devuelve el período inmediatamente anterior de la misma longitud."""
    inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
    fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date()

    if inicio.day == 1 and fin.day == calendar.monthrange(fin.year, fin.month)[1]:
        mes = inicio.month - 1 if inicio.month > 1 else 12
        anio = inicio.year if inicio.month > 1 else inicio.year - 1
        ultimo_dia_anterior = calendar.monthrange(anio, mes)[1]
        inicio_anterior = datetime(anio, mes, 1).date()
        fin_anterior = datetime(anio, mes, ultimo_dia_anterior).date()
        return inicio_anterior.isoformat(), fin_anterior.isoformat()

    duracion = (fin - inicio).days + 1
    inicio_anterior = inicio - timedelta(days=duracion)
    fin_anterior = inicio - timedelta(days=1)
    return inicio_anterior.isoformat(), fin_anterior.isoformat()


def _contar_tareas_pendientes(cursor, fecha_inicio, fecha_fin, usuario):
    condiciones = [
        "t.estado IN ('PENDIENTE', 'EN_PROCESO', 'EN_REVISION')",
        "t.fecha_creacion >= %s",
        "t.fecha_creacion < DATE_ADD(%s, INTERVAL 1 DAY)",
    ]
    parametros = [fecha_inicio, fecha_fin]

    if usuario["nombre_rol"] != ROL_ADMINISTRADOR:
        condiciones.append("t.id_responsable = %s")
        parametros.append(usuario["id_usuario"])

    sql = f"""
        SELECT COUNT(*) AS total
        FROM tarea t
        WHERE {' AND '.join(condiciones)}
    """
    cursor.execute(sql, tuple(parametros))
    fila = cursor.fetchone()
    return int((fila or {}).get("total", 0) or 0)


def _url_detalle_tarea(id_tarea):
    return f"/frontend/tareas/detalle_tarea.html?id={id_tarea}"


def _puede_operar_tarea(usuario, id_responsable):
    """Mismo criterio de acceso que el detalle (RF63) y la edición (RF64):
    un ADMINISTRADOR opera sobre cualquier tarea; el resto, solo sobre las
    tareas de las que es responsable. Se aplica en el servidor para que no
    dependa de qué botones muestra el listado."""
    return (
        usuario["nombre_rol"] == ROL_ADMINISTRADOR
        or usuario["id_usuario"] == id_responsable
    )


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

    if prioridad not in ("BAJA", "MEDIA", "ALTA", "URGENTE"):
        return jsonify({"error": "Prioridad no válida"}), 400
    if fecha_vencimiento:
        try:
            datetime.strptime(fecha_vencimiento, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "La fecha de vencimiento no es válida"}), 400

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

        cursor.execute("SELECT id_cliente FROM cliente WHERE id_cliente = %s", (id_cliente,))
        if not cursor.fetchone():
            return jsonify({"error": "Cliente inexistente"}), 404

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

            # RF52 — la asignación inicial también es una nueva asignación:
            # se avisa al responsable, salvo que se haya asignado a sí mismo.
            crear_notificacion(
                cursor,
                int(id_responsable),
                "ASIGNACION_TAREA",
                f"Se te asignó la nueva tarea \"{titulo}\"",
                _url_detalle_tarea(cursor.lastrowid),
                id_usuario_actor=id_creador,
            )

        connection.commit()

        mensaje = "Tarea creada correctamente"
        if len(areas) > 1:
            mensaje = "Tareas creadas correctamente"

        return jsonify({
            "message": mensaje
        }), 201

    except Exception:
        if connection:
            connection.rollback()
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

    # RF69 — Filtrando Tareas por Estado. Sin filtro se conserva el
    # comportamiento de siempre (solo las tareas no finalizadas); con un
    # estado explícito se acota a ese estado exacto, incluidos COMPLETADA y
    # CANCELADA, que el listado por defecto no muestra.
    estado_filtro = request.args.get("estado")

    if estado_filtro and estado_filtro not in ESTADOS_VALIDOS:
        return jsonify({"error": "Estado no válido"}), 400

    # RF68 — Visualizando Tareas Asignadas a un Usuario Específico. Quien no
    # es ADMINISTRADOR solo puede pedir sus propias tareas por este filtro.
    id_responsable_filtro = request.args.get("id_responsable")

    if id_responsable_filtro:
        try:
            id_responsable_filtro = int(id_responsable_filtro)
        except ValueError:
            return jsonify({"error": "id_responsable debe ser un número"}), 400

        if (
            usuario["nombre_rol"] != ROL_ADMINISTRADOR
            and id_responsable_filtro != usuario["id_usuario"]
        ):
            return jsonify({"error": "No tiene acceso a las tareas de otro usuario"}), 403

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        if estado_filtro:
            condiciones = ["t.estado = %s"]
            parametros = [estado_filtro]
        else:
            condiciones = ["t.estado IN ('PENDIENTE', 'EN_PROCESO', 'EN_REVISION')"]
            parametros = []

        # Un usuario no administrador solo debe ver sus propias tareas: el
        # frontend (tareas.js) ya filtraba esto en el navegador, pero eso no
        # impedía que cualquier autenticado pidiera este endpoint directo y
        # recibiera las tareas de todas las áreas. Se aplica la misma regla
        # en el servidor.
        if id_responsable_filtro:
            condiciones.append("t.id_responsable = %s")
            parametros.append(id_responsable_filtro)
        elif usuario["nombre_rol"] != ROL_ADMINISTRADOR:
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
        if connection:
            connection.rollback()
        logger.exception("Error al listar tareas pendientes")
        return jsonify({"error": "Error interno al listar tareas"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/pendientes/resumen", methods=["GET"])
@login_required
def resumen_tareas_pendientes_dashboard():
    """RF36 — Indicadores de carga de trabajo en tareas pendientes."""
    connection = None
    cursor = None
    usuario = obtener_usuario_actual()

    fecha_inicio, fecha_fin, error = _validar_rango_tareas(request.args)
    if error:
        return jsonify({"error": error}), 400

    if fecha_inicio is None and fecha_fin is None:
        hoy = datetime.today().date()
        fecha_inicio = datetime(hoy.year, hoy.month, 1).date().isoformat()
        fecha_fin = datetime(hoy.year, hoy.month, calendar.monthrange(hoy.year, hoy.month)[1]).date().isoformat()

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        condiciones = ["t.estado IN ('PENDIENTE', 'EN_PROCESO', 'EN_REVISION')"]
        parametros = []

        if usuario["nombre_rol"] != ROL_ADMINISTRADOR:
            condiciones.append("t.id_responsable = %s")
            parametros.append(usuario["id_usuario"])

        where = " WHERE " + " AND ".join(condiciones)
        total_sql = f"SELECT COUNT(*) AS total FROM tarea t{where}"
        cursor.execute(total_sql, tuple(parametros))
        total_pendientes = int((cursor.fetchone() or {}).get("total", 0) or 0)

        area_sql = f"""
            SELECT a.id_area, a.nombre_area AS nombre_area, COUNT(*) AS total
            FROM tarea t
            INNER JOIN area a ON t.id_area = a.id_area
            {where}
            GROUP BY a.id_area, a.nombre_area
            ORDER BY total DESC, a.nombre_area ASC
        """
        cursor.execute(area_sql, tuple(parametros))
        por_area = [
            {"area": fila.get("nombre_area") or fila.get("area"), "total": int(fila["total"])}
            for fila in cursor.fetchall()
        ]

        cliente_sql = f"""
            SELECT c.id_cliente, c.razon_social AS razon_social, COUNT(*) AS total
            FROM tarea t
            INNER JOIN cliente c ON t.id_cliente = c.id_cliente
            {where}
            GROUP BY c.id_cliente, c.razon_social
            ORDER BY total DESC, c.razon_social ASC
        """
        cursor.execute(cliente_sql, tuple(parametros))
        por_cliente = [
            {
                "id_cliente": fila["id_cliente"],
                "cliente": fila.get("razon_social") or fila.get("cliente"),
                "total": int(fila["total"]),
            }
            for fila in cursor.fetchall()
        ]

        responsable_sql = f"""
            SELECT u.id_usuario AS id_responsable, u.nombres AS nombres, COUNT(*) AS total
            FROM tarea t
            INNER JOIN usuario u ON t.id_responsable = u.id_usuario
            {where}
            GROUP BY u.id_usuario, u.nombres
            ORDER BY total DESC, u.nombres ASC
        """
        cursor.execute(responsable_sql, tuple(parametros))
        por_responsable = [
            {
                "id_responsable": fila.get("id_responsable") or fila.get("id_usuario"),
                "responsable": fila.get("nombres") or fila.get("responsable"),
                "total": int(fila["total"]),
            }
            for fila in cursor.fetchall()
        ]

        inicio_periodo, fin_periodo = _rango_periodo_anterior(fecha_inicio, fecha_fin)
        total_anterior = _contar_tareas_pendientes(cursor, inicio_periodo, fin_periodo, usuario)
        diferencia = total_pendientes - total_anterior
        comparacion = {
            "disponible": total_pendientes > 0 or total_anterior > 0,
            "periodo_actual": {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
            "periodo_anterior": {"fecha_inicio": inicio_periodo, "fecha_fin": fin_periodo},
            "diferencia": diferencia,
        }

        if total_pendientes == 0 and not por_area and not por_cliente and not por_responsable:
            return jsonify({
                "total_pendientes": 0,
                "por_area": [],
                "por_cliente": [],
                "por_responsable": [],
                "comparacion": {
                    "disponible": False,
                    "periodo_actual": None,
                    "periodo_anterior": None,
                    "diferencia": 0,
                },
            }), 200

        return jsonify({
            "total_pendientes": total_pendientes,
            "por_area": por_area,
            "por_cliente": por_cliente,
            "por_responsable": por_responsable,
            "comparacion": comparacion,
        }), 200

    except Exception:
        logger.exception("Error al calcular el resumen de tareas pendientes")
        return jsonify({"error": "Error interno al calcular el resumen"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/<int:id_tarea>", methods=["GET"])
@login_required
def obtener_tarea(id_tarea):
    """RF63 — Visualizando el Detalle Completo de Tarea."""
    connection = None
    cursor = None
    usuario = obtener_usuario_actual()

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                t.id_tarea,
                t.id_cliente,
                t.id_area,
                t.id_responsable,
                t.id_creador,
                t.titulo,
                t.descripcion,
                t.estado,
                t.prioridad,
                t.fecha_creacion,
                t.fecha_vencimiento,
                t.fecha_inicio,
                t.fecha_finalizacion,
                t.observaciones,
                c.razon_social AS cliente,
                u.nombres AS responsable,
                cr.nombres AS creador,
                a.nombre_area AS area
            FROM tarea t
            INNER JOIN cliente c ON t.id_cliente = c.id_cliente
            INNER JOIN usuario u ON t.id_responsable = u.id_usuario
            INNER JOIN usuario cr ON t.id_creador = cr.id_usuario
            INNER JOIN area a ON t.id_area = a.id_area
            WHERE t.id_tarea = %s
            """,
            (id_tarea,)
        )
        tarea = cursor.fetchone()

        if not tarea:
            return jsonify({"error": "Tarea no encontrada"}), 404

        # Un usuario sin rol ADMINISTRADOR solo puede abrir el detalle de
        # tareas donde es responsable (RF63).
        if (
            usuario["nombre_rol"] != ROL_ADMINISTRADOR
            and usuario["id_usuario"] != tarea["id_responsable"]
        ):
            return jsonify({"error": "No tiene acceso a esta tarea"}), 403

        # El historial de cambios se arma a partir de auditoria: no existe una
        # columna id_tarea allí, así que se filtra por el mismo prefijo que ya
        # escribe la reasignación masiva ("id_tarea=<id>, ..."), tanto en el
        # valor anterior como en el nuevo.
        patron_tarea = f"id_tarea={id_tarea},%"
        cursor.execute(
            """
            SELECT a.accion, a.datos_anteriores, a.datos_nuevos, a.fecha, u.nombres AS usuario
            FROM auditoria a
            INNER JOIN usuario u ON u.id_usuario = a.id_usuario
            WHERE a.tabla_afectada = 'tarea'
              AND (a.datos_anteriores LIKE %s OR a.datos_nuevos LIKE %s)
            ORDER BY a.fecha DESC
            """,
            (patron_tarea, patron_tarea)
        )
        tarea["historial"] = cursor.fetchall()

        return jsonify(tarea), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al obtener detalle de tarea")
        return jsonify({"error": "Error interno al obtener la tarea"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def _fecha_a_date(valor):
    """Normaliza a `date` tanto el datetime/date que entrega mysql-connector
    como el texto ISO que devuelve SQLite en los tests."""
    if isinstance(valor, str):
        return datetime.strptime(valor[:10], "%Y-%m-%d").date()
    if isinstance(valor, datetime):
        return valor.date()
    return valor


@tareas_bp.route("/tareas/<int:id_tarea>", methods=["PUT"])
@login_required
def editar_tarea(id_tarea):
    """RF64 — Editando Tareas Existentes."""
    connection = None
    cursor = None
    data = request.get_json()
    usuario = obtener_usuario_actual()

    titulo = (data.get("titulo") or "").strip()
    descripcion = data.get("descripcion")
    id_responsable = data.get("id_responsable")
    prioridad = data.get("prioridad")
    fecha_vencimiento = data.get("fecha_vencimiento") or None

    prioridades_validas = ["BAJA", "MEDIA", "ALTA", "URGENTE"]

    if not titulo:
        return jsonify({"error": "El título es obligatorio"}), 400

    if not id_responsable:
        return jsonify({"error": "Debe seleccionar un responsable"}), 400

    try:
        id_responsable = int(id_responsable)
    except (TypeError, ValueError):
        return jsonify({"error": "El responsable seleccionado no es válido"}), 400

    if prioridad not in prioridades_validas:
        return jsonify({"error": "Prioridad no válida"}), 400

    if fecha_vencimiento:
        try:
            fecha_vencimiento_valor = datetime.strptime(fecha_vencimiento, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "La fecha de vencimiento no es válida"}), 400

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT id_tarea, id_responsable, titulo, descripcion, estado,
                   prioridad, fecha_vencimiento, fecha_creacion
            FROM tarea
            WHERE id_tarea = %s
            """,
            (id_tarea,)
        )
        tarea = cursor.fetchone()

        if not tarea:
            return jsonify({"error": "Tarea no encontrada"}), 404

        # Mismo criterio de acceso que el detalle (RF63): quien no es
        # ADMINISTRADOR solo puede tocar sus propias tareas.
        if (
            usuario["nombre_rol"] != ROL_ADMINISTRADOR
            and usuario["id_usuario"] != tarea["id_responsable"]
        ):
            return jsonify({"error": "No tiene acceso a esta tarea"}), 403

        if tarea["estado"] in ESTADOS_FINALES:
            return jsonify({
                "error": "No se puede editar una tarea COMPLETADA o CANCELADA"
            }), 409

        if fecha_vencimiento:
            fecha_creacion_valor = _fecha_a_date(tarea["fecha_creacion"])

            if fecha_vencimiento_valor < fecha_creacion_valor:
                return jsonify({
                    "error": "La fecha de vencimiento no puede ser anterior a la fecha de creación"
                }), 400

        cursor.execute(
            """
            SELECT id_usuario, estado
            FROM usuario
            WHERE id_usuario = %s
            """,
            (id_responsable,)
        )
        responsable = cursor.fetchone()

        if not responsable or responsable["estado"] != "ACTIVO":
            return jsonify({"error": "El responsable seleccionado no es válido"}), 422

        valor_anterior_vencimiento = (
            str(tarea["fecha_vencimiento"]) if tarea["fecha_vencimiento"] else None
        )

        cambios = [
            ("titulo", tarea["titulo"], titulo),
            ("descripcion", tarea["descripcion"], descripcion),
            ("id_responsable", tarea["id_responsable"], id_responsable),
            ("prioridad", tarea["prioridad"], prioridad),
            ("fecha_vencimiento", valor_anterior_vencimiento, fecha_vencimiento),
        ]

        cursor.execute(
            """
            UPDATE tarea
            SET titulo = %s, descripcion = %s, id_responsable = %s,
                prioridad = %s, fecha_vencimiento = %s
            WHERE id_tarea = %s
            """,
            (titulo, descripcion, id_responsable, prioridad, fecha_vencimiento, id_tarea)
        )

        for campo, valor_anterior, valor_nuevo in cambios:
            if valor_anterior == valor_nuevo:
                continue

            registrar_auditoria(
                cursor, usuario["id_usuario"], "tarea", "EDICION",
                id_registro=id_tarea,
                datos_anteriores=f"id_tarea={id_tarea}, {campo}={valor_anterior}",
                datos_nuevos=f"id_tarea={id_tarea}, {campo}={valor_nuevo}",
            )

        # RF52 — cambiar el responsable desde la edición también es una
        # reasignación: el nuevo responsable recibe el aviso.
        if id_responsable != tarea["id_responsable"]:
            crear_notificacion(
                cursor,
                id_responsable,
                "REASIGNACION_TAREA",
                f"Se te asignó la tarea \"{titulo}\"",
                _url_detalle_tarea(id_tarea),
                id_usuario_actor=usuario["id_usuario"],
            )

        connection.commit()

        return jsonify({"message": "Tarea actualizada correctamente"}), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al editar tarea")
        return jsonify({"error": "Error interno al editar la tarea"}), 500

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
        "SELECT id_responsable, estado FROM tarea WHERE id_tarea = %s",
        (id_tarea,)
    )
    tarea = cursor.fetchone()

    if not tarea:
        return False, "Tarea no encontrada", 404, None

    # RF64/RF65: el cierre bloquea modificaciones también por la ruta masiva.
    if tarea[1] in ESTADOS_FINALES:
        return False, "No se puede reasignar una tarea COMPLETADA o CANCELADA", 409, None

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
    """RF16 — Modificando la Asignación de Tareas."""
    connection = None
    cursor = None
    data = request.get_json()
    usuario = obtener_usuario_actual()

    id_responsable = data.get("id_responsable")

    if not id_responsable:
        return jsonify({"error": "Debe seleccionar un responsable"}), 400

    try:
        id_responsable = int(id_responsable)
    except (TypeError, ValueError):
        return jsonify({"error": "El responsable seleccionado no es válido"}), 400

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT estado, titulo, id_responsable FROM tarea WHERE id_tarea = %s",
            (id_tarea,)
        )
        tarea = cursor.fetchone()

        if not tarea:
            return jsonify({"error": "Tarea no encontrada"}), 404

        estado_actual, titulo_tarea, id_responsable_actual = tarea

        # Antes cualquier usuario autenticado podía reasignar cualquier tarea
        # cambiando el id en la URL. Se exige el mismo acceso que RF63/RF64.
        if not _puede_operar_tarea(usuario, id_responsable_actual):
            return jsonify({"error": "No tiene acceso a esta tarea"}), 403

        if estado_actual in ESTADOS_FINALES:
            return jsonify({
                "error": "No se puede reasignar una tarea COMPLETADA o CANCELADA"
            }), 409

        ok, error, status, id_responsable_anterior = _reasignar_tarea(
            cursor, id_tarea, id_responsable
        )

        if not ok:
            return jsonify({"error": error}), status

        # El cambio queda en auditoria con responsable anterior, nuevo y
        # fecha (columna con default en la propia tabla).
        registrar_auditoria(
            cursor, usuario["id_usuario"], "tarea", "REASIGNACION",
            id_registro=id_tarea,
            datos_anteriores=f"id_tarea={id_tarea}, id_responsable={id_responsable_anterior}",
            datos_nuevos=f"id_tarea={id_tarea}, id_responsable={id_responsable}",
        )

        # El nuevo responsable recibe una notificación (RF52), salvo que se
        # haya autoasignado la tarea.
        crear_notificacion(
            cursor,
            id_responsable,
            "REASIGNACION_TAREA",
            f"Se te asignó la tarea \"{titulo_tarea}\"",
            _url_detalle_tarea(id_tarea),
            id_usuario_actor=usuario["id_usuario"],
        )

        connection.commit()

        # La existencia de la tarea ya se confirmó arriba: si rowcount es 0
        # en el UPDATE es porque el responsable nuevo es igual al que ya
        # tenía (MySQL solo cuenta filas realmente modificadas), no porque
        # no exista. Es un no-op válido, no un 404.

        return jsonify({"message": "Tarea asignada correctamente"}), 200

    except Exception:
        if connection:
            connection.rollback()
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

    if estado not in ESTADOS_VALIDOS:
        return jsonify({"error": "Estado no válido"}), 400

    if estado in ESTADOS_FINALES and usuario["nombre_rol"] != ROL_ADMINISTRADOR:
        return jsonify({
            "error": "Solo un administrador puede aplicar estados finales"
        }), 403

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT estado, id_responsable, titulo FROM tarea WHERE id_tarea = %s",
            (id_tarea,)
        )
        tarea = cursor.fetchone()

        if not tarea:
            return jsonify({"error": "Tarea no encontrada"}), 404

        # Quien no es ADMINISTRADOR solo cambia el estado de sus propias
        # tareas: el listado solo le muestra esas, y el servidor lo exige.
        if not _puede_operar_tarea(usuario, tarea["id_responsable"]):
            return jsonify({"error": "No tiene acceso a esta tarea"}), 403

        estado_anterior = tarea["estado"]
        if estado_anterior == estado:
            return jsonify({"message": "Estado actualizado correctamente"}), 200
        if estado_anterior in ESTADOS_FINALES:
            return jsonify({"error": "No se puede modificar una tarea COMPLETADA o CANCELADA"}), 409

        if estado == "COMPLETADA":
            # RF65 — Marcando Tarea como Completada: además de cerrar el
            # estado se registra la hora exacta del cierre; quién la
            # completó queda en auditoria, igual que el resto de los
            # cambios sobre tarea (RF64, RF16).
            cursor.execute(
                """
                UPDATE tarea
                SET estado = %s, fecha_finalizacion = CURRENT_TIMESTAMP
                WHERE id_tarea = %s
                """,
                (estado, id_tarea)
            )
            registrar_auditoria(
                cursor, usuario["id_usuario"], "tarea", "COMPLETAR_TAREA",
                id_registro=id_tarea,
                datos_anteriores=f"id_tarea={id_tarea}, estado={estado_anterior}",
                datos_nuevos=f"id_tarea={id_tarea}, estado=COMPLETADA",
            )
        else:
            cursor.execute(
                "UPDATE tarea SET estado = %s WHERE id_tarea = %s",
                (estado, id_tarea)
            )
            # La cancelación también cierra la tarea (bloquea la edición,
            # igual que RF65): queda en el historial quién la canceló.
            if estado == "CANCELADA":
                registrar_auditoria(
                    cursor, usuario["id_usuario"], "tarea", "CANCELAR_TAREA",
                    id_registro=id_tarea,
                    datos_anteriores=f"id_tarea={id_tarea}, estado={estado_anterior}",
                    datos_nuevos=f"id_tarea={id_tarea}, estado=CANCELADA",
                )

        # RF51 — el responsable se entera del cambio de estado, salvo que lo
        # haya hecho él mismo o que el estado no haya cambiado realmente.
        if estado != estado_anterior:
            crear_notificacion(
                cursor,
                tarea["id_responsable"],
                "CAMBIO_ESTADO_TAREA",
                f"La tarea \"{tarea['titulo']}\" cambió de {estado_anterior} a {estado}",
                _url_detalle_tarea(id_tarea),
                id_usuario_actor=usuario["id_usuario"],
            )

        connection.commit()

        return jsonify({"message": "Estado actualizado correctamente"}), 200

    except Exception:
        if connection:
            connection.rollback()
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
    usuario = obtener_usuario_actual()

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

        cursor.execute("SELECT estado, id_responsable, prioridad FROM tarea WHERE id_tarea = %s", (id_tarea,))
        tarea = cursor.fetchone()
        if not tarea:
            return jsonify({"error": "Tarea no encontrada"}), 404
        if not _puede_operar_tarea(usuario, tarea[1]):
            return jsonify({"error": "No tiene acceso a esta tarea"}), 403
        if tarea[0] in ESTADOS_FINALES:
            return jsonify({"error": "No se puede editar una tarea COMPLETADA o CANCELADA"}), 409

        sql = """
            UPDATE tarea
            SET prioridad = %s
            WHERE id_tarea = %s
        """

        cursor.execute(sql, (prioridad, id_tarea))

        # Mismo registro que deja la edición (RF64) cuando cambia la
        # prioridad, para que el historial del detalle (RF63) lo muestre.
        if tarea[2] != prioridad:
            registrar_auditoria(
                cursor, usuario["id_usuario"], "tarea", "EDICION",
                id_registro=id_tarea,
                datos_anteriores=f"id_tarea={id_tarea}, prioridad={tarea[2]}",
                datos_nuevos=f"id_tarea={id_tarea}, prioridad={prioridad}",
            )

        connection.commit()

        return jsonify({"message": "Prioridad actualizada correctamente"}), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al actualizar prioridad de tarea")
        return jsonify({"error": "Error interno al actualizar prioridad"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/carga", methods=["GET"])
@roles_required(ROL_ADMINISTRADOR)
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
            f"SELECT id_usuario FROM usuario WHERE id_usuario IN ({marcadores})",
            tuple(ids_usuario)
        )
        if len(cursor.fetchall()) != len(ids_usuario):
            return jsonify({"error": "Uno o más usuarios no existen"}), 404

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
        if connection:
            connection.rollback()
        logger.exception("Error al consultar la carga de trabajo")
        return jsonify({"error": "Error interno al consultar la carga de trabajo"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/vencidas", methods=["GET"])
@login_required
def tareas_vencidas():
    """RF42 — Visualizando Tareas Vencidas.

    Tareas no finalizadas cuya fecha de vencimiento ya pasó. Mismo criterio de
    visibilidad que /tareas/pendientes: quien no es ADMINISTRADOR solo ve las
    suyas.
    """
    connection = None
    cursor = None
    usuario = obtener_usuario_actual()

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        condiciones = [
            "t.fecha_vencimiento < CURDATE()",
            f"t.estado NOT IN ({', '.join(['%s'] * len(ESTADOS_FINALES))})",
        ]
        parametros = list(ESTADOS_FINALES)

        if usuario["nombre_rol"] != ROL_ADMINISTRADOR:
            condiciones.append("t.id_responsable = %s")
            parametros.append(usuario["id_usuario"])

        sql = f"""
            SELECT
                t.id_tarea,
                t.titulo,
                t.estado,
                t.prioridad,
                t.fecha_vencimiento,
                c.razon_social AS cliente,
                u.nombres AS responsable,
                DATEDIFF(CURDATE(), t.fecha_vencimiento) AS dias_retraso
            FROM tarea t
            INNER JOIN cliente c ON t.id_cliente = c.id_cliente
            INNER JOIN usuario u ON t.id_responsable = u.id_usuario
            WHERE {" AND ".join(condiciones)}
            ORDER BY dias_retraso DESC
        """

        cursor.execute(sql, tuple(parametros))
        tareas = cursor.fetchall()

        return jsonify(tareas), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al listar tareas vencidas")
        return jsonify({"error": "Error interno al listar tareas vencidas"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/por-vencer", methods=["GET"])
@login_required
def tareas_por_vencer():
    """RF43 — Visualizando Tareas Próximas a Vencer.

    Tareas no finalizadas cuya fecha de vencimiento cae dentro de los
    próximos `dias` días (parámetro configurable, no fijo en el código).
    No repite las que ya están vencidas (RF42): esas quedan estrictamente
    antes de hoy, así que el rango de este endpoint parte de hoy inclusive.
    """
    connection = None
    cursor = None
    usuario = obtener_usuario_actual()

    dias_texto = request.args.get("dias", "7")

    try:
        dias = int(dias_texto)
    except ValueError:
        return jsonify({"error": "dias debe ser un número entero"}), 400

    if dias <= 0:
        return jsonify({"error": "dias debe ser mayor que cero"}), 400

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        condiciones = [
            "t.fecha_vencimiento >= CURDATE()",
            "t.fecha_vencimiento < DATE_ADD(CURDATE(), INTERVAL %s DAY)",
            f"t.estado NOT IN ({', '.join(['%s'] * len(ESTADOS_FINALES))})",
        ]
        parametros = [dias + 1, *ESTADOS_FINALES]

        if usuario["nombre_rol"] != ROL_ADMINISTRADOR:
            condiciones.append("t.id_responsable = %s")
            parametros.append(usuario["id_usuario"])

        sql = f"""
            SELECT
                t.id_tarea,
                t.titulo,
                t.estado,
                t.prioridad,
                t.fecha_vencimiento,
                c.razon_social AS cliente,
                u.nombres AS responsable,
                DATEDIFF(t.fecha_vencimiento, CURDATE()) AS dias_restantes
            FROM tarea t
            INNER JOIN cliente c ON t.id_cliente = c.id_cliente
            INNER JOIN usuario u ON t.id_responsable = u.id_usuario
            WHERE {" AND ".join(condiciones)}
            ORDER BY t.fecha_vencimiento ASC
        """

        cursor.execute(sql, tuple(parametros))
        tareas = cursor.fetchall()

        return jsonify(tareas), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al listar tareas próximas a vencer")
        return jsonify({"error": "Error interno al listar tareas próximas a vencer"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/prioritarias", methods=["GET"])
@login_required
def tareas_prioritarias():
    """RF48 — Visualizando Tareas Prioritarias.

    Tareas de prioridad ALTA o URGENTE, solo del usuario autenticado (no las
    de otros, ni siquiera si es ADMINISTRADOR): a diferencia de /vencidas y
    /por-vencer, aquí no hay vista "de todos".
    """
    connection = None
    cursor = None
    usuario = obtener_usuario_actual()

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                t.id_tarea,
                t.titulo,
                t.estado,
                t.prioridad,
                t.fecha_vencimiento,
                c.razon_social AS cliente
            FROM tarea t
            INNER JOIN cliente c ON t.id_cliente = c.id_cliente
            WHERE t.id_responsable = %s
              AND t.prioridad IN ('ALTA', 'URGENTE')
              AND t.estado NOT IN ('COMPLETADA', 'CANCELADA')
            ORDER BY
                FIELD(t.prioridad, 'URGENTE', 'ALTA'),
                t.fecha_vencimiento ASC
            """,
            (usuario["id_usuario"],)
        )
        tareas = cursor.fetchall()

        return jsonify(tareas), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al listar tareas prioritarias")
        return jsonify({"error": "Error interno al listar tareas prioritarias"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/resumen", methods=["GET"])
@login_required
def resumen_tareas_dashboard():
    """RF50 — Resumiendo por Estado de Tareas.

    Conteo por cada uno de los cinco estados, incluidos los que estén en
    cero (mismo patrón que resumen_clientes_dashboard en clientes_routes.py).
    Un ADMINISTRADOR ve el total del sistema; el resto, solo lo suyo.
    """
    connection = None
    cursor = None
    usuario = obtener_usuario_actual()

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        condiciones = []
        parametros = []

        if usuario["nombre_rol"] != ROL_ADMINISTRADOR:
            condiciones.append("id_responsable = %s")
            parametros.append(usuario["id_usuario"])

        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

        cursor.execute(
            f"""
            SELECT estado, COUNT(*) AS total
            FROM tarea
            {where}
            GROUP BY estado
            """,
            tuple(parametros)
        )
        conteos = {fila["estado"]: fila["total"] for fila in cursor.fetchall()}

        resumen = {estado: conteos.get(estado, 0) for estado in ESTADOS_VALIDOS}

        return jsonify(resumen), 200

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al generar resumen de tareas por estado")
        return jsonify({"error": "Error interno al generar el resumen"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@tareas_bp.route("/tareas/reasignar-masivo", methods=["PUT"])
@roles_required(ROL_ADMINISTRADOR)
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
        id_responsable = int(id_responsable)
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

            registrar_auditoria(
                cursor, usuario["id_usuario"], "tarea", "REASIGNACION_MASIVA",
                id_registro=id_tarea,
                datos_anteriores=f"id_tarea={id_tarea}, id_responsable={id_responsable_anterior}",
                datos_nuevos=f"id_tarea={id_tarea}, id_responsable={id_responsable}",
            )

            # RF52 — cada tarea que cambia de manos se avisa al nuevo
            # responsable, igual que en la reasignación individual (RF16).
            if id_responsable_anterior != id_responsable:
                cursor.execute("SELECT titulo FROM tarea WHERE id_tarea = %s", (id_tarea,))
                fila_titulo = cursor.fetchone()
                crear_notificacion(
                    cursor,
                    id_responsable,
                    "REASIGNACION_TAREA",
                    f"Se te asignó la tarea \"{fila_titulo[0] if fila_titulo else id_tarea}\"",
                    _url_detalle_tarea(id_tarea),
                    id_usuario_actor=usuario["id_usuario"],
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
