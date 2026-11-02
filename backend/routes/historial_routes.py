"""RF56 — Historiando la Actividad y RF30 — Historial de accesos y modificaciones.

Historial global de actividad del sistema, de solo lectura y visible solo
para administradores (Documento 0, Tablas 7.56 y 7.30). Se arma sobre la
tabla AUDITORIA a través de backend/utils/auditoria.py; este módulo no
expone rutas de escritura: el historial no se puede modificar ni eliminar.
Los filtros por usuario, fecha y acción (RF30) se combinan con AND.
"""
import logging
import re

from flask import Blueprint, jsonify, request

from backend.config.db import get_connection
from backend.routes.reportes_routes import _validar_periodo
from backend.utils.auditoria import consultar_auditoria, modulos_disponibles, tablas_de_modulo
from backend.utils.auth import ROL_ADMINISTRADOR, roles_required
from backend.utils.auditoria import modulo_de_tabla

historial_bp = Blueprint("historial", __name__)
logger = logging.getLogger(__name__)

POR_PAGINA_DEFECTO = 25
POR_PAGINA_MAXIMO = 100
CAMBIOS_RECIENTES_LIMITE = 10

# Las acciones son constantes en MAYÚSCULAS con guion bajo (LOGIN,
# CLIENTE_CREADO...). Validar la forma evita filtros con texto arbitrario;
# el valor igualmente viaja como parámetro SQL.
PATRON_ACCION = re.compile(r"^[A-Z0-9_]{1,50}$")


def _entero_positivo(valor, defecto):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return defecto
    return numero if numero > 0 else defecto


def leer_filtros_historial(args):
    """Valida los filtros comunes del historial (RF56 y RF40).

    Devuelve (filtros, error). `filtros` trae las claves que acepta
    consultar_auditoria(): tablas, id_usuario, acciones, fecha_inicio y fecha_fin.
    """
    filtros = {}

    modulo = (args.get("modulo") or "").strip()
    if modulo:
        if modulo not in modulos_disponibles():
            return None, "El módulo indicado no existe."
        filtros["tablas"] = tablas_de_modulo(modulo)

    id_usuario = (args.get("id_usuario") or "").strip()
    if id_usuario:
        if not id_usuario.isdigit():
            return None, "El usuario indicado no es válido."
        filtros["id_usuario"] = int(id_usuario)

    accion = (args.get("accion") or "").strip()
    if accion:
        if not PATRON_ACCION.match(accion):
            return None, "La acción indicada no es válida."
        filtros["acciones"] = [accion]

    if (args.get("fecha_inicio") or "").strip() or (args.get("fecha_fin") or "").strip():
        fecha_inicio, fecha_fin, error = _validar_periodo(args)
        if error:
            return None, error
        filtros["fecha_inicio"] = fecha_inicio
        filtros["fecha_fin"] = fecha_fin

    return filtros, None


@historial_bp.route("/historial", methods=["GET"])
@roles_required(ROL_ADMINISTRADOR)
def listar_historial():
    filtros, error = leer_filtros_historial(request.args)
    if error:
        return jsonify({"error": error}), 400

    pagina = _entero_positivo(request.args.get("pagina"), 1)
    por_pagina = min(_entero_positivo(request.args.get("por_pagina"), POR_PAGINA_DEFECTO), POR_PAGINA_MAXIMO)

    connection = None
    cursor = None
    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "Error de conexión con la base de datos"}), 500

        cursor = connection.cursor(dictionary=True)
        eventos, total = consultar_auditoria(
            cursor, limite=por_pagina, offset=(pagina - 1) * por_pagina, **filtros
        )

        return jsonify({
            "eventos": eventos,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": max(1, -(-total // por_pagina)),
        }), 200

    except Exception:
        logger.exception("Error al consultar el historial de actividad")
        return jsonify({"error": "Error interno al consultar el historial"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@historial_bp.route("/historial/filtros", methods=["GET"])
@roles_required(ROL_ADMINISTRADOR)
def opciones_filtros_historial():
    """Opciones para los selectores de la vista: módulos, usuarios y acciones."""
    connection = None
    cursor = None
    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "Error de conexión con la base de datos"}), 500

        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id_usuario, nombres FROM usuario ORDER BY nombres")
        usuarios = cursor.fetchall()

        # RF30: solo las acciones que ya existen en el historial.
        cursor.execute("SELECT DISTINCT accion FROM auditoria ORDER BY accion")
        acciones = [fila["accion"] for fila in cursor.fetchall()]

        return jsonify({
            "modulos": modulos_disponibles(),
            "usuarios": usuarios,
            "acciones": acciones,
        }), 200

    except Exception:
        logger.exception("Error al consultar los filtros del historial")
        return jsonify({"error": "Error interno al consultar los filtros"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def _leer_filtros_cambios_recientes(args):
    modulo = (args.get("modulo") or "").strip()
    accion = (args.get("accion") or "").strip()

    if modulo and modulo not in modulos_disponibles():
        return None, "El módulo indicado no existe."
    if accion and not PATRON_ACCION.fullmatch(accion):
        return None, "La acción indicada no es válida."

    tablas = tablas_de_modulo(modulo) if modulo else None
    return {"tablas": tablas, "accion": accion or None}, None


def _formatear_fecha_cambio(valor):
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d"), valor.strftime("%H:%M:%S")
    fecha_hora = str(valor or "")
    return fecha_hora[:10], fecha_hora[11:19] if len(fecha_hora) >= 19 else ""


@historial_bp.route("/cambios-recientes", methods=["GET"])
@roles_required(ROL_ADMINISTRADOR)
def listar_cambios_recientes():
    filtros, error = _leer_filtros_cambios_recientes(request.args)
    if error:
        return jsonify({"error": error}), 400

    condiciones = []
    parametros = []
    if filtros["tablas"] is not None:
        condiciones.append(
            f"a.tabla_afectada IN ({', '.join(['%s'] * len(filtros['tablas']))})"
        )
        parametros.extend(filtros["tablas"])
    if filtros["accion"]:
        condiciones.append("a.accion = %s")
        parametros.append(filtros["accion"])
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

    connection = None
    cursor = None
    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "Error de conexión con la base de datos"}), 500

        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            f"""
            SELECT a.id_auditoria, a.fecha, u.nombres AS usuario,
                   a.tabla_afectada, a.id_registro, a.accion,
                   c.id_cliente AS cliente_disponible,
                   t.id_tarea AS tarea_disponible
            FROM auditoria a
            LEFT JOIN usuario u ON u.id_usuario = a.id_usuario
            LEFT JOIN cliente c
              ON a.tabla_afectada = 'cliente' AND c.id_cliente = a.id_registro
            LEFT JOIN tarea t
              ON a.tabla_afectada = 'tarea' AND t.id_tarea = a.id_registro
            {where}
            ORDER BY a.fecha DESC, a.id_auditoria DESC
            LIMIT %s
            """,
            tuple(parametros + [CAMBIOS_RECIENTES_LIMITE]),
        )
        filas = cursor.fetchall()

        cambios = []
        for fila in filas:
            fecha, hora = _formatear_fecha_cambio(fila.get("fecha"))
            tabla = fila.get("tabla_afectada")
            id_registro = fila.get("id_registro")
            tipo_registro = None
            if tabla == "cliente" and fila.get("cliente_disponible") is not None:
                tipo_registro = "cliente"
            elif tabla == "tarea" and fila.get("tarea_disponible") is not None:
                tipo_registro = "tarea"

            cambios.append({
                "id_auditoria": fila.get("id_auditoria"),
                "tipo": fila.get("accion"),
                "modulo": modulo_de_tabla(tabla),
                "fecha": fecha,
                "hora": hora,
                "usuario": fila.get("usuario") or "Usuario no disponible",
                "tipo_registro": tipo_registro,
                "id_registro": id_registro if tipo_registro else None,
            })

        return jsonify({"cambios": cambios, "limite": CAMBIOS_RECIENTES_LIMITE}), 200
    except Exception:
        logger.exception("Error al consultar cambios recientes")
        return jsonify({"error": "Error interno al consultar cambios recientes"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@historial_bp.route("/cambios-recientes/filtros", methods=["GET"])
@roles_required(ROL_ADMINISTRADOR)
def opciones_filtros_cambios_recientes():
    connection = None
    cursor = None
    try:
        connection = get_connection()
        if connection is None:
            return jsonify({"error": "Error de conexión con la base de datos"}), 500

        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT DISTINCT accion FROM auditoria ORDER BY accion")
        acciones = [fila["accion"] for fila in cursor.fetchall()]
        return jsonify({"modulos": modulos_disponibles(), "tipos": acciones}), 200
    except Exception:
        logger.exception("Error al consultar filtros de cambios recientes")
        return jsonify({"error": "Error interno al consultar filtros"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
