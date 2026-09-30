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

historial_bp = Blueprint("historial", __name__)
logger = logging.getLogger(__name__)

POR_PAGINA_DEFECTO = 25
POR_PAGINA_MAXIMO = 100

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
