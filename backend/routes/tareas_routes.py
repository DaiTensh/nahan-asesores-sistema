import logging
from datetime import datetime

from flask import Blueprint, request, jsonify
from backend.config.db import get_connection
from backend.routes.notificaciones_routes import crear_notificacion
from backend.utils.auth import ROL_ADMINISTRADOR, login_required, obtener_usuario_actual

tareas_bp = Blueprint("tareas", __name__)
logger = logging.getLogger(__name__)

ESTADOS_FINALES = {"COMPLETADA", "CANCELADA"}
ESTADOS_VALIDOS = ["PENDIENTE", "EN_PROCESO", "EN_REVISION", "COMPLETADA", "CANCELADA"]


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
        logger.exception("Error al listar tareas pendientes")
        return jsonify({"error": "Error interno al listar tareas"}), 500

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

            cursor.execute(
                """
                INSERT INTO auditoria (id_usuario, tabla_afectada, accion, datos_anteriores, datos_nuevos)
                VALUES (%s, 'tarea', 'EDICION', %s, %s)
                """,
                (
                    usuario["id_usuario"],
                    f"id_tarea={id_tarea}, {campo}={valor_anterior}",
                    f"id_tarea={id_tarea}, {campo}={valor_nuevo}"
                )
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
    """RF16 — Modificando la Asignación de Tareas."""
    connection = None
    cursor = None
    data = request.get_json()
    usuario = obtener_usuario_actual()

    id_responsable = data.get("id_responsable")

    if not id_responsable:
        return jsonify({"error": "Debe seleccionar un responsable"}), 400

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT estado, titulo FROM tarea WHERE id_tarea = %s",
            (id_tarea,)
        )
        tarea = cursor.fetchone()

        if not tarea:
            return jsonify({"error": "Tarea no encontrada"}), 404

        estado_actual, titulo_tarea = tarea

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
        cursor.execute(
            """
            INSERT INTO auditoria (id_usuario, tabla_afectada, accion, datos_anteriores, datos_nuevos)
            VALUES (%s, 'tarea', 'REASIGNACION', %s, %s)
            """,
            (
                usuario["id_usuario"],
                f"id_tarea={id_tarea}, id_responsable={id_responsable_anterior}",
                f"id_tarea={id_tarea}, id_responsable={id_responsable}"
            )
        )

        # El nuevo responsable recibe una notificación (RF52), salvo que se
        # haya autoasignado la tarea.
        crear_notificacion(
            cursor,
            id_responsable,
            "REASIGNACION_TAREA",
            f"Se te asignó la tarea \"{titulo_tarea}\"",
            f"/frontend/tareas/detalle_tarea.html?id={id_tarea}",
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

        estado_anterior = tarea["estado"]

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
            cursor.execute(
                """
                INSERT INTO auditoria (id_usuario, tabla_afectada, accion, datos_anteriores, datos_nuevos)
                VALUES (%s, 'tarea', 'COMPLETAR_TAREA', %s, %s)
                """,
                (
                    usuario["id_usuario"],
                    f"id_tarea={id_tarea}, estado={estado_anterior}",
                    f"id_tarea={id_tarea}, estado=COMPLETADA"
                )
            )
        else:
            cursor.execute(
                "UPDATE tarea SET estado = %s WHERE id_tarea = %s",
                (estado, id_tarea)
            )

        # RF51 — el responsable se entera del cambio de estado, salvo que lo
        # haya hecho él mismo o que el estado no haya cambiado realmente.
        if estado != estado_anterior:
            crear_notificacion(
                cursor,
                tarea["id_responsable"],
                "CAMBIO_ESTADO_TAREA",
                f"La tarea \"{tarea['titulo']}\" cambió de {estado_anterior} a {estado}",
                f"/frontend/tareas/detalle_tarea.html?id={id_tarea}",
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
        logger.exception("Error al listar tareas vencidas")
        return jsonify({"error": "Error interno al listar tareas vencidas"}), 500

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
