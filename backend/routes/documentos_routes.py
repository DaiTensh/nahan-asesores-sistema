import logging
import os
import uuid

from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

from backend.config.db import get_connection
from backend.utils.auth import ROL_ADMINISTRADOR, login_required, obtener_usuario_actual

documentos_bp = Blueprint("documentos", __name__)
logger = logging.getLogger(__name__)

TAMANO_MAXIMO_MB_DEFAULT = 10
EXTENSIONES_PERMITIDAS_DEFAULT = "pdf,doc,docx,xls,xlsx,ppt,pptx,jpg,jpeg,png"


def _directorio_adjuntos():
    # Fuera del repositorio (o ignorado por git): en el EC2 apunta al volumen
    # montado para esto, en local cae por defecto a uploads/tareas.
    ruta = os.getenv("ADJUNTOS_DIR", "").strip() or os.path.join(os.getcwd(), "uploads", "tareas")
    os.makedirs(ruta, exist_ok=True)
    return ruta


def _config_adjuntos(cursor):
    cursor.execute(
        """
        SELECT nombre_parametro, valor_parametro
        FROM parametros_sistema
        WHERE nombre_parametro IN (
            'ADJUNTOS_TAMANO_MAXIMO_MB',
            'ADJUNTOS_EXTENSIONES_PERMITIDAS'
        )
        """
    )
    filas = {fila["nombre_parametro"]: fila["valor_parametro"] for fila in cursor.fetchall()}

    try:
        tamano_maximo_mb = int(filas.get("ADJUNTOS_TAMANO_MAXIMO_MB", TAMANO_MAXIMO_MB_DEFAULT))
    except (TypeError, ValueError):
        tamano_maximo_mb = TAMANO_MAXIMO_MB_DEFAULT

    extensiones_texto = filas.get("ADJUNTOS_EXTENSIONES_PERMITIDAS", EXTENSIONES_PERMITIDAS_DEFAULT)
    extensiones_permitidas = {
        ext.strip().lower() for ext in extensiones_texto.split(",") if ext.strip()
    }

    return tamano_maximo_mb, extensiones_permitidas


def _extension(nombre_archivo):
    if "." not in nombre_archivo:
        return ""
    return nombre_archivo.rsplit(".", 1)[-1].lower()


def _usuario_tiene_acceso_a_tarea(usuario, tarea):
    return (
        usuario["nombre_rol"] == ROL_ADMINISTRADOR
        or usuario["id_usuario"] == tarea["id_responsable"]
        or usuario["id_usuario"] == tarea["id_creador"]
    )


@documentos_bp.route("/tareas/<int:id_tarea>/documentos", methods=["POST"])
@login_required
def subir_documento_tarea(id_tarea):
    connection = None
    cursor = None
    usuario = obtener_usuario_actual()

    archivo = request.files.get("archivo")

    if not archivo or not archivo.filename:
        return jsonify({"error": "Debe adjuntar un archivo"}), 400

    nombre_original = secure_filename(archivo.filename)

    if not nombre_original:
        return jsonify({"error": "El nombre del archivo no es válido"}), 400

    extension = _extension(nombre_original)

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT id_cliente, id_responsable, id_creador
            FROM tarea
            WHERE id_tarea = %s
            """,
            (id_tarea,)
        )
        tarea = cursor.fetchone()

        if not tarea:
            return jsonify({"error": "Tarea no encontrada"}), 404

        if not _usuario_tiene_acceso_a_tarea(usuario, tarea):
            return jsonify({"error": "No tiene acceso a esta tarea"}), 403

        tamano_maximo_mb, extensiones_permitidas = _config_adjuntos(cursor)

        if extension not in extensiones_permitidas:
            return jsonify({
                "error": f"Tipo de archivo no permitido. Extensiones permitidas: "
                         f"{', '.join(sorted(extensiones_permitidas))}"
            }), 400

        archivo.stream.seek(0, os.SEEK_END)
        tamano_bytes = archivo.stream.tell()
        archivo.stream.seek(0)

        if tamano_bytes == 0:
            return jsonify({"error": "El archivo está vacío"}), 400

        if tamano_bytes > tamano_maximo_mb * 1024 * 1024:
            return jsonify({
                "error": f"El archivo supera el tamaño máximo permitido ({tamano_maximo_mb} MB)"
            }), 400

        # El nombre en disco no depende del nombre original: evita choques y,
        # junto con secure_filename, cierra cualquier intento de path
        # traversal (rutas relativas o "..") desde el nombre que llega del
        # cliente.
        nombre_guardado = f"{uuid.uuid4().hex}.{extension}" if extension else uuid.uuid4().hex
        directorio = _directorio_adjuntos()
        ruta_absoluta = os.path.join(directorio, nombre_guardado)

        archivo.save(ruta_absoluta)

        try:
            cursor.execute(
                """
                INSERT INTO documento (
                    id_cliente, nombre_documento, url_archivo, subido_por
                )
                VALUES (%s, %s, %s, %s)
                """,
                (tarea["id_cliente"], nombre_original, nombre_guardado, usuario["id_usuario"])
            )
            id_documento = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO tarea_documento (id_tarea, id_documento)
                VALUES (%s, %s)
                """,
                (id_tarea, id_documento)
            )

            connection.commit()
        except Exception:
            if os.path.exists(ruta_absoluta):
                os.remove(ruta_absoluta)
            raise

        return jsonify({
            "message": "Archivo adjuntado correctamente",
            "id_documento": id_documento,
            "nombre_documento": nombre_original
        }), 201

    except Exception:
        logger.exception("Error al subir documento de tarea")
        return jsonify({"error": "Error interno al subir el archivo"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
