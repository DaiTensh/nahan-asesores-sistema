from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, request
from backend.config.db import get_connection


control_horas_bp = Blueprint("control_horas", __name__)

ROLES_PERMITIDOS = {
    "ADMINISTRADOR",
    "USUARIO_AREA_JURIDICA",
    "USUARIO_AREA_CONTABLE",
}
TARIFA_GLOBAL_DEFAULT = Decimal("30000.00")


def _obtener_id_usuario(origen):
    try:
        id_usuario = int(origen.get("id_usuario"))
    except (TypeError, ValueError):
        return None

    return id_usuario if id_usuario > 0 else None


def _obtener_usuario(cursor, id_usuario, bloquear=False):
    bloqueo = " FOR UPDATE" if bloquear else ""
    cursor.execute(
        f"""
        SELECT u.id_usuario, u.estado, r.nombre_rol
        FROM usuario u
        INNER JOIN rol r ON u.id_rol = r.id_rol
        WHERE u.id_usuario = %s{bloqueo}
        """,
        (id_usuario,),
    )
    return cursor.fetchone()


def _validar_usuario(usuario):
    if not usuario or usuario["estado"] != "ACTIVO":
        return "La sesión no corresponde a un usuario activo."

    if usuario["nombre_rol"] not in ROLES_PERMITIDOS:
        return "No tiene permisos para acceder a este módulo."

    return None


def _obtener_tarifa_vigente(cursor, id_area):
    cursor.execute(
        """
        SELECT valor_hora
        FROM tarifa_hora
        WHERE id_area = %s
          AND estado = 'ACTIVA'
          AND fecha_inicio <= CURRENT_DATE
          AND (fecha_fin IS NULL OR fecha_fin >= CURRENT_DATE)
        ORDER BY fecha_inicio DESC, id_tarifa DESC
        LIMIT 1
        """,
        (id_area,),
    )
    tarifa = cursor.fetchone()

    if tarifa:
        return Decimal(tarifa["valor_hora"])

    cursor.execute(
        """
        SELECT valor_parametro
        FROM parametros_sistema
        WHERE nombre_parametro = 'TARIFA_HORA_DEFAULT'
        LIMIT 1
        """
    )
    parametro = cursor.fetchone()

    if not parametro:
        return TARIFA_GLOBAL_DEFAULT

    try:
        return Decimal(parametro["valor_parametro"])
    except (InvalidOperation, TypeError, ValueError):
        return TARIFA_GLOBAL_DEFAULT


def _serializar_registro(registro):
    for campo in ("duracion_minutos", "tarifa_hora", "monto"):
        if registro.get(campo) is not None:
            registro[campo] = float(registro[campo])
    return registro


def _consultar_temporizador_activo(cursor, id_usuario):
    cursor.execute(
        """
        SELECT
            rt.id_registro,
            rt.id_tarea,
            rt.id_cliente,
            t.titulo AS tarea,
            c.razon_social AS cliente,
            DATE_FORMAT(
                TIMESTAMP(rt.fecha, rt.hora_inicio),
                '%Y-%m-%dT%H:%i:%S'
            ) AS inicio,
            rt.tarifa_hora
        FROM registro_tiempo rt
        INNER JOIN tarea t ON rt.id_tarea = t.id_tarea
        INNER JOIN cliente c ON rt.id_cliente = c.id_cliente
        WHERE rt.id_usuario = %s
          AND rt.hora_fin IS NULL
        ORDER BY rt.id_registro DESC
        LIMIT 1
        """,
        (id_usuario,),
    )
    temporizador = cursor.fetchone()
    return _serializar_registro(temporizador) if temporizador else None


@control_horas_bp.route("/control-horas/contexto", methods=["GET"])
def obtener_contexto():
    id_usuario = _obtener_id_usuario(request.args)

    if not id_usuario:
        return jsonify({"error": "Usuario no válido."}), 400

    connection = None
    cursor = None

    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "No se pudo conectar con la base de datos."}), 500

        cursor = connection.cursor(dictionary=True)
        usuario = _obtener_usuario(cursor, id_usuario)
        error_usuario = _validar_usuario(usuario)

        if error_usuario:
            return jsonify({"error": error_usuario}), 403

        condiciones = [
            "t.estado IN ('PENDIENTE', 'EN_PROCESO', 'EN_REVISION')",
            "c.estado = 'ACTIVO'",
        ]
        parametros = []

        if usuario["nombre_rol"] != "ADMINISTRADOR":
            condiciones.append("t.id_responsable = %s")
            parametros.append(id_usuario)

        cursor.execute(
            f"""
            SELECT
                t.id_tarea,
                t.id_cliente,
                t.titulo,
                c.razon_social AS cliente
            FROM tarea t
            INNER JOIN cliente c ON t.id_cliente = c.id_cliente
            WHERE {" AND ".join(condiciones)}
            ORDER BY c.razon_social ASC, t.titulo ASC
            """,
            tuple(parametros),
        )
        tareas = cursor.fetchall()
        temporizador = _consultar_temporizador_activo(cursor, id_usuario)

        return jsonify({
            "tareas": tareas,
            "temporizador_activo": temporizador,
        }), 200

    except Exception as error:
        return jsonify({"error": str(error)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@control_horas_bp.route("/control-horas/iniciar", methods=["POST"])
def iniciar_temporizador():
    datos = request.get_json(silent=True) or {}
    id_usuario = _obtener_id_usuario(datos)

    try:
        id_tarea = int(datos.get("id_tarea"))
    except (TypeError, ValueError):
        id_tarea = None

    if not id_usuario or not id_tarea or id_tarea < 1:
        return jsonify({"error": "Usuario y tarea son obligatorios."}), 400

    connection = None
    cursor = None

    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "No se pudo conectar con la base de datos."}), 500

        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        usuario = _obtener_usuario(cursor, id_usuario, bloquear=True)
        error_usuario = _validar_usuario(usuario)

        if error_usuario:
            connection.rollback()
            return jsonify({"error": error_usuario}), 403

        temporizador_activo = _consultar_temporizador_activo(cursor, id_usuario)
        if temporizador_activo:
            connection.rollback()
            return jsonify({
                "error": "Ya existe un temporizador activo para este usuario."
            }), 409

        condiciones = [
            "t.id_tarea = %s",
            "t.estado IN ('PENDIENTE', 'EN_PROCESO', 'EN_REVISION')",
            "c.estado = 'ACTIVO'",
        ]
        parametros = [id_tarea]

        if usuario["nombre_rol"] != "ADMINISTRADOR":
            condiciones.append("t.id_responsable = %s")
            parametros.append(id_usuario)

        cursor.execute(
            f"""
            SELECT
                t.id_tarea,
                t.id_cliente,
                t.id_area,
                t.titulo,
                c.razon_social AS cliente
            FROM tarea t
            INNER JOIN cliente c ON t.id_cliente = c.id_cliente
            WHERE {" AND ".join(condiciones)}
            LIMIT 1
            """,
            tuple(parametros),
        )
        tarea = cursor.fetchone()

        if not tarea:
            connection.rollback()
            return jsonify({
                "error": "La tarea no existe o no está disponible para este usuario."
            }), 404

        tarifa_hora = _obtener_tarifa_vigente(cursor, tarea["id_area"])

        cursor.execute(
            """
            INSERT INTO registro_tiempo (
                id_usuario,
                id_cliente,
                id_tarea,
                fecha,
                hora_inicio,
                tarifa_hora
            )
            VALUES (%s, %s, %s, CURRENT_DATE, CURRENT_TIME, %s)
            """,
            (
                id_usuario,
                tarea["id_cliente"],
                tarea["id_tarea"],
                tarifa_hora,
            ),
        )
        id_registro = cursor.lastrowid
        connection.commit()

        cursor.execute(
            """
            SELECT
                rt.id_registro,
                rt.id_tarea,
                rt.id_cliente,
                t.titulo AS tarea,
                c.razon_social AS cliente,
                DATE_FORMAT(
                    TIMESTAMP(rt.fecha, rt.hora_inicio),
                    '%Y-%m-%dT%H:%i:%S'
                ) AS inicio,
                rt.tarifa_hora
            FROM registro_tiempo rt
            INNER JOIN tarea t ON rt.id_tarea = t.id_tarea
            INNER JOIN cliente c ON rt.id_cliente = c.id_cliente
            WHERE rt.id_registro = %s
            """,
            (id_registro,),
        )
        temporizador = _serializar_registro(cursor.fetchone())

        return jsonify({
            "message": "Temporizador iniciado correctamente.",
            "temporizador_activo": temporizador,
        }), 201

    except Exception as error:
        if connection:
            connection.rollback()
        return jsonify({"error": str(error)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@control_horas_bp.route("/control-horas/detener", methods=["POST"])
def detener_temporizador():
    datos = request.get_json(silent=True) or {}
    id_usuario = _obtener_id_usuario(datos)

    if not id_usuario:
        return jsonify({"error": "Usuario no válido."}), 400

    connection = None
    cursor = None

    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "No se pudo conectar con la base de datos."}), 500

        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        usuario = _obtener_usuario(cursor, id_usuario, bloquear=True)
        error_usuario = _validar_usuario(usuario)

        if error_usuario:
            connection.rollback()
            return jsonify({"error": error_usuario}), 403

        cursor.execute(
            """
            SELECT id_registro
            FROM registro_tiempo
            WHERE id_usuario = %s
              AND hora_fin IS NULL
            ORDER BY id_registro DESC
            LIMIT 1
            FOR UPDATE
            """,
            (id_usuario,),
        )
        registro = cursor.fetchone()

        if not registro:
            connection.rollback()
            return jsonify({"error": "No existe un temporizador activo."}), 404

        cursor.execute(
            """
            UPDATE registro_tiempo
            SET
                hora_fin = CURRENT_TIME,
                duracion_minutos = ROUND(
                    TIMESTAMPDIFF(
                        SECOND,
                        TIMESTAMP(fecha, hora_inicio),
                        CURRENT_TIMESTAMP
                    ) / 60,
                    2
                )
            WHERE id_registro = %s
            """,
            (registro["id_registro"],),
        )
        connection.commit()

        cursor.execute(
            """
            SELECT
                id_registro,
                duracion_minutos,
                tarifa_hora,
                monto
            FROM registro_tiempo
            WHERE id_registro = %s
            """,
            (registro["id_registro"],),
        )
        registro_final = _serializar_registro(cursor.fetchone())

        return jsonify({
            "message": "Horas y monto registrados correctamente.",
            "registro": registro_final,
        }), 200

    except Exception as error:
        if connection:
            connection.rollback()
        return jsonify({"error": str(error)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@control_horas_bp.route("/control-horas/registros", methods=["GET"])
def listar_registros():
    id_usuario = _obtener_id_usuario(request.args)

    if not id_usuario:
        return jsonify({"error": "Usuario no válido."}), 400

    connection = None
    cursor = None

    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "No se pudo conectar con la base de datos."}), 500

        cursor = connection.cursor(dictionary=True)
        usuario = _obtener_usuario(cursor, id_usuario)
        error_usuario = _validar_usuario(usuario)

        if error_usuario:
            return jsonify({"error": error_usuario}), 403

        condiciones = ["rt.hora_fin IS NOT NULL"]
        parametros = []

        if usuario["nombre_rol"] != "ADMINISTRADOR":
            condiciones.append("rt.id_usuario = %s")
            parametros.append(id_usuario)

        cursor.execute(
            f"""
            SELECT
                rt.id_registro,
                t.titulo AS tarea,
                c.razon_social AS cliente,
                DATE_FORMAT(
                    TIMESTAMP(rt.fecha, rt.hora_inicio),
                    '%d-%m-%Y %H:%i:%S'
                ) AS inicio,
                DATE_FORMAT(rt.hora_fin, '%H:%i:%S') AS fin,
                rt.duracion_minutos,
                rt.tarifa_hora,
                rt.monto,
                u.nombres AS usuario_responsable
            FROM registro_tiempo rt
            INNER JOIN tarea t ON rt.id_tarea = t.id_tarea
            INNER JOIN cliente c ON rt.id_cliente = c.id_cliente
            INNER JOIN usuario u ON rt.id_usuario = u.id_usuario
            WHERE {" AND ".join(condiciones)}
            ORDER BY rt.fecha DESC, rt.hora_inicio DESC
            """,
            tuple(parametros),
        )
        registros = [_serializar_registro(fila) for fila in cursor.fetchall()]

        cursor.execute(
            f"""
            SELECT
                COALESCE(SUM(rt.duracion_minutos), 0) AS minutos_acumulados,
                COALESCE(SUM(rt.monto), 0) AS monto_acumulado
            FROM registro_tiempo rt
            WHERE {" AND ".join(condiciones)}
            """,
            tuple(parametros),
        )
        resumen = cursor.fetchone()

        cursor.execute(
            f"""
            SELECT
                c.razon_social AS nombre,
                COALESCE(SUM(rt.duracion_minutos), 0) AS minutos,
                COALESCE(SUM(rt.monto), 0) AS monto
            FROM registro_tiempo rt
            INNER JOIN cliente c ON rt.id_cliente = c.id_cliente
            WHERE {" AND ".join(condiciones)}
            GROUP BY rt.id_cliente, c.razon_social
            ORDER BY c.razon_social ASC
            """,
            tuple(parametros),
        )
        totales_cliente = cursor.fetchall()

        cursor.execute(
            f"""
            SELECT
                t.titulo AS nombre,
                COALESCE(SUM(rt.duracion_minutos), 0) AS minutos,
                COALESCE(SUM(rt.monto), 0) AS monto
            FROM registro_tiempo rt
            INNER JOIN tarea t ON rt.id_tarea = t.id_tarea
            WHERE {" AND ".join(condiciones)}
            GROUP BY rt.id_tarea, t.titulo
            ORDER BY t.titulo ASC
            """,
            tuple(parametros),
        )
        totales_tarea = cursor.fetchall()

        return jsonify({
            "registros": registros,
            "resumen": {
                "minutos_acumulados": float(resumen["minutos_acumulados"]),
                "monto_acumulado": float(resumen["monto_acumulado"]),
                "totales_cliente": [
                    {
                        "nombre": total["nombre"],
                        "minutos": float(total["minutos"]),
                        "monto": float(total["monto"]),
                    }
                    for total in totales_cliente
                ],
                "totales_tarea": [
                    {
                        "nombre": total["nombre"],
                        "minutos": float(total["minutos"]),
                        "monto": float(total["monto"]),
                    }
                    for total in totales_tarea
                ],
            },
        }), 200

    except Exception as error:
        return jsonify({"error": str(error)}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
