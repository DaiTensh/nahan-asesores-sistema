import logging
import io

from mysql.connector import IntegrityError

from flask import Blueprint, request, jsonify, send_file
from openpyxl import Workbook
from datetime import datetime
from backend.config.db import get_connection
from backend.utils.auditoria import registrar_auditoria, consultar_auditoria
from backend.utils.auth import ROL_ADMINISTRADOR, ROLES_OPERATIVOS, obtener_usuario_actual, roles_required

clientes_blueprint = Blueprint('clientes_blueprint', __name__)
logger = logging.getLogger(__name__)

@clientes_blueprint.route('/clientes', methods=['POST'])
@roles_required(*ROLES_OPERATIVOS)
def registrar_cliente():
    conexion = None
    try:
        datos = request.json
        
        rut = (datos.get('rut') or '').strip()
        razon_social = (datos.get('razon_social') or '').strip()
        email = (datos.get('email') or '').strip()
        telefono = (datos.get('telefono') or '').strip()
        direccion = (datos.get('direccion') or '').strip()
        areas = datos.get('areas', []) # Array de IDs de áreas [1, 2]

        # Validaciones de campos obligatorios según esquema de BD
        if not all([rut, razon_social]):
            return jsonify({"error": "RUT y Nombre de contacto 1 (Razón Social) son estrictamente obligatorios."}), 400

        if not areas:
            return jsonify({"error": "Debe asignar el cliente a por lo menos un área activa."}), 400

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo interno de comunicación con la base de datos."}), 500

        with conexion.cursor() as cursor:
            # Control preventivo de RUT duplicado
            cursor.execute("SELECT id_cliente FROM cliente WHERE rut = %s", (rut,))
            if cursor.fetchone():
                return jsonify({"error": "El RUT ingresado ya pertenece a un cliente registrado."}), 400

            # 1. Insertar el cliente en la tabla base
            query_cliente = """
                INSERT INTO cliente (rut, razon_social, email, telefono, direccion, estado)
                VALUES (%s, %s, %s, %s, %s, 'ACTIVO')
            """
            cursor.execute(query_cliente, (rut, razon_social, email, telefono, direccion))
            
            # Obtener el id_cliente recién generado
            id_nuevo_cliente = cursor.lastrowid

            # 2. Insertar las relaciones en la tabla intermedia cliente_area
            query_area = """
                INSERT INTO cliente_area (id_cliente, id_area, fecha_asignacion)
                VALUES (%s, %s, %s)
            """
            fecha_hoy = datetime.now().date()
            for id_area in areas:
                cursor.execute(query_area, (id_nuevo_cliente, id_area, fecha_hoy))
            
            conexion.commit()

        return jsonify({"message": "Cliente incorporado exitosamente junto a sus áreas asociadas."}), 201

    except IntegrityError as error:
        if conexion:
            conexion.rollback()
        if error.errno == 1062:
            return jsonify({"error": "Ya existe un registro con esos datos únicos"}), 400
        if error.errno == 1452:
            return jsonify({"error": "Un rol o área indicada no existe"}), 422
        logger.exception("Error de integridad al guardar datos")
        return jsonify({"error": "Error interno al guardar datos"}), 500

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al registrar cliente")
        return jsonify({"error": "Ocurrió una anomalía interna en el servidor al guardar el expediente."}), 500

    finally:
        if conexion:
            conexion.close()


@clientes_blueprint.route('/clientes/<int:id_cliente>', methods=['GET'])
@roles_required(*ROLES_OPERATIVOS)
def obtener_cliente(id_cliente):
    conexion = None
    try:
        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            # 1. Traer datos base de la tabla cliente
            cursor.execute("""
                SELECT id_cliente, rut, razon_social, email, telefono, direccion, estado
                FROM cliente
                WHERE id_cliente = %s
            """, (id_cliente,))
            cliente = cursor.fetchone()

            if not cliente:
                return jsonify({"error": "El expediente solicitado no existe."}), 404

            # 2. Buscar relaciones en la tabla intermedia cliente_area
            cursor.execute("SELECT id_area FROM cliente_area WHERE id_cliente = %s", (id_cliente,))
            filas_areas = cursor.fetchall()
            
            # Formateamos los IDs de las áreas en una lista simple: [1, 2]
            cliente['areas'] = [item['id_area'] for item in filas_areas]

        return jsonify(cliente), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al obtener cliente")
        return jsonify({"error": "Error interno del servidor."}), 500

    finally:
        if conexion:
            conexion.close()




@clientes_blueprint.route('/clientes/<int:id_cliente>', methods=['PUT'])
@roles_required(*ROLES_OPERATIVOS)
def modificar_cliente(id_cliente):
    conexion = None
    try:
        datos = request.json
        razon_social = (datos.get('razon_social') or '').strip()
        email = (datos.get('email') or '').strip()
        telefono = (datos.get('telefono') or '').strip()
        direccion = (datos.get('direccion') or '').strip()
        areas = datos.get('areas', []) # Arreglo de enteros [1] o [2] o [1,2]

        if not razon_social:
            return jsonify({"error": "El campo Nombre contacto 1 es mandatorio."}), 400

        if not areas:
            return jsonify({"error": "Debe mantener al menos una asignación de área."}), 400

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Error de base de datos."}), 500

        with conexion.cursor() as cursor:
            # Verificar existencia del cliente
            cursor.execute("SELECT id_cliente FROM cliente WHERE id_cliente = %s", (id_cliente,))
            if not cursor.fetchone():
                return jsonify({"error": "Cliente inexistente."}), 404

            # 1. Actualizar tabla base cliente
            query_update = """
                UPDATE cliente 
                SET razon_social = %s, email = %s, telefono = %s, direccion = %s
                WHERE id_cliente = %s
            """
            cursor.execute(query_update, (razon_social, email, telefono, direccion, id_cliente))

            # 2. Sincronizar tabla intermedia (Limpiar previas e insertar nuevas asignaciones)
            cursor.execute("DELETE FROM cliente_area WHERE id_cliente = %s", (id_cliente,))
            
            query_insert_area = """
                INSERT INTO cliente_area (id_cliente, id_area, fecha_asignacion)
                VALUES (%s, %s, CURRENT_DATE)
            """
            for id_area in areas:
                cursor.execute(query_insert_area, (id_cliente, id_area))

            conexion.commit()

        return jsonify({"message": "Expediente modificado con éxito."}), 200

    except IntegrityError as error:
        if conexion:
            conexion.rollback()
        if error.errno == 1062:
            return jsonify({"error": "Ya existe un registro con esos datos únicos"}), 400
        if error.errno == 1452:
            return jsonify({"error": "Un rol o área indicada no existe"}), 422
        logger.exception("Error de integridad al guardar datos")
        return jsonify({"error": "Error interno al guardar datos"}), 500

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al modificar cliente")
        return jsonify({"error": "Error inesperado al almacenar cambios."}), 500

    finally:
        if conexion:
            conexion.close()



# ==========================================================================
# RF03: ENPOINT DE VERIFICACIÓN DE VÍNCULOS COMERCIALES
# ==========================================================================
@clientes_blueprint.route('/clientes/<int:id_cliente>/verificar-vinculos', methods=['GET'])
@roles_required(ROL_ADMINISTRADOR)
def verificar_vinculos_cliente(id_cliente):
    conexion = None
    try:
        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Error de base de datos."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            # 1. Traer datos básicos
            cursor.execute("SELECT rut, razon_social FROM cliente WHERE id_cliente = %s", (id_cliente,))
            cliente = cursor.fetchone()
            if not cliente:
                return jsonify({"error": "Cliente no localizado."}), 404

            # 2. Contar tareas en proceso o pendientes según tus ENUM de BD
            query_tareas = """
                SELECT COUNT(*) as conteo FROM tarea 
                WHERE id_cliente = %s AND estado IN ('PENDIENTE', 'EN_PROCESO', 'EN_REVISION')
            """
            cursor.execute(query_tareas, (id_cliente,))
            total_tareas = cursor.fetchone()['conteo']

            # 3. Contar documentos activos vigentes
            query_docs = "SELECT COUNT(*) as conteo FROM documento WHERE id_cliente = %s AND estado = 'ACTIVO'"
            cursor.execute(query_docs, (id_cliente,))
            total_docs = cursor.fetchone()['conteo']

            vinculos_activos = (total_tareas > 0 or total_docs > 0)

        return jsonify({
            "rut": cliente['rut'],
            "razon_social": cliente['razon_social'],
            "tiene_vinculos": vinculos_activos,
            "tareas_activas": total_tareas,
            "documentos_activos": total_docs
        }), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error en verificación de vínculos de cliente")
        return jsonify({"error": "Error al calcular dependencias."}), 500

    finally:
        if conexion:
            conexion.close()


# ==========================================================================
# RF03: ACCIÓN A - DESHABILITACIÓN LÓGICA (CON VÍNCULOS) + AUDITORÍA
# ==========================================================================
@clientes_blueprint.route('/clientes/<int:id_cliente>/deshabilitar', methods=['PATCH'])
@roles_required(ROL_ADMINISTRADOR)
def deshabilitar_cliente_rf3(id_cliente):
    conexion = None
    try:
        usuario_actual = obtener_usuario_actual()
        id_usuario = usuario_actual["id_usuario"]
        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo interno de comunicación con la base de datos."}), 500

        with conexion.cursor() as cursor:
            # Modificar estado a INACTIVO (solo si el cliente existe)
            cursor.execute("UPDATE cliente SET estado = 'INACTIVO' WHERE id_cliente = %s", (id_cliente,))

            if cursor.rowcount == 0:
                conexion.rollback()
                return jsonify({"error": "Cliente inexistente."}), 404

            # Grabar en historial (Tabla Auditoria de tu base de datos)
            registrar_auditoria(
                cursor, id_usuario, "cliente", "DESHABILITAR",
                id_registro=id_cliente,
                datos_anteriores="estado: ACTIVO",
                datos_nuevos="estado: INACTIVO",
            )
            conexion.commit()

        return jsonify({"message": "Cliente deshabilitado y registrado en auditoría."}), 200
    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error procesando deshabilitación de cliente")
        return jsonify({"error": "Error procesando deshabilitación."}), 500

    finally:
        if conexion:
            conexion.close()


# ==========================================================================
# RF03: ACCIÓN B - ELIMINACIÓN DEFINITIVA FÍSICA (SIN VÍNCULOS) + AUDITORÍA
# ==========================================================================
@clientes_blueprint.route('/clientes/<int:id_cliente>/eliminar-definitivo', methods=['DELETE'])
@roles_required(ROL_ADMINISTRADOR)
def eliminar_definitivo_cliente(id_cliente):
    conexion = None
    try:
        usuario_actual = obtener_usuario_actual()
        id_usuario = usuario_actual["id_usuario"]
        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo interno de comunicación con la base de datos."}), 500

        with conexion.cursor() as cursor:
            # Resguardar datos para el log histórico antes de eliminarlos físicamente
            cursor.execute("SELECT rut, razon_social FROM cliente WHERE id_cliente = %s", (id_cliente,))
            info = cursor.fetchone()

            if not info:
                return jsonify({"error": "Cliente inexistente."}), 404
            
            log_anterior = f"rut: {info[0]}, razon_social: {info[1]}"

            # 1. Limpiar amarras en la tabla intermedia cliente_area para evitar error de FK
            cursor.execute("DELETE FROM cliente_area WHERE id_cliente = %s", (id_cliente,))

            # 2. Remover físicamente de la tabla cliente
            cursor.execute("DELETE FROM cliente WHERE id_cliente = %s", (id_cliente,))

            # 3. Grabar en historial de auditoría
            registrar_auditoria(
                cursor, id_usuario, "cliente", "ELIMINACION_DEFINITIVA",
                id_registro=id_cliente,
                datos_anteriores=log_anterior,
                datos_nuevos="REMOVIDO_COMPLETAMENTE",
            )
            conexion.commit()

        return jsonify({"message": "Cliente eliminado físicamente y registrado en auditoría."}), 200
    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error en eliminación definitiva de cliente")
        return jsonify({"error": "No se pudo realizar la eliminación por dependencias."}), 500

    finally:
        if conexion:
            conexion.close()

# ==========================================================================
# RF04: VISUALIZANDO LA FICHA COMPLETA Y CONSOLIDADA DEL CLIENTE
# ==========================================================================
@clientes_blueprint.route('/clientes/<int:id_cliente>/ficha', methods=['GET'])
@roles_required(*ROLES_OPERATIVOS)
def obtener_ficha_consolidada(id_cliente):
    conexion = None
    try:
        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Error interno de base de datos."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            # 1. Traer la información base del cliente
            cursor.execute("SELECT id_cliente, rut, razon_social, email, telefono, direccion, estado FROM cliente WHERE id_cliente = %s", (id_cliente,))
            cliente = cursor.fetchone()
            
            if not cliente:
                return jsonify({"error": "El expediente solicitado no existe en los registros activos."}), 404

            # 2. Consultar las áreas asociadas concatenando sus nombres de forma limpia
            query_areas = """
                SELECT a.nombre_area FROM cliente_area ca
                JOIN area a ON ca.id_area = a.id_area
                WHERE ca.id_cliente = %s
            """
            cursor.execute(query_areas, (id_cliente,))
            areas_filas = cursor.fetchall()
            nombres_areas = [f["nombre_area"] for f in areas_filas]
            cliente["areas_nombres"] = ", ".join(nombres_areas) if nombres_areas else "Sin área asignada"

            # 3. Traer el historial completo de tareas vinculadas
            query_tareas = """
                SELECT t.titulo, t.estado, DATE_FORMAT(t.fecha_vencimiento, '%d-%m-%Y') as fecha_vencimiento, a.nombre_area
                FROM tarea t
                JOIN area a ON t.id_area = a.id_area
                WHERE t.id_cliente = %s
                ORDER BY t.fecha_creacion DESC
            """
            cursor.execute(query_tareas, (id_cliente,))
            cliente["tareas"] = cursor.fetchall()

            # RF61 — Panel resumen: cantidad de tareas activas, calculada sobre
            # el mismo listado ya traído (sin disparar una consulta adicional).
            cliente["tareas_activas"] = sum(
                1 for tarea in cliente["tareas"] if tarea["estado"] in ("PENDIENTE", "EN_PROCESO")
            )

            # 4. Traer las referencias documentales del cliente (RF07/RF08).
            # Solo las filas con tipo_documento son referencias registradas
            # por RF07: los adjuntos de tarea (RF54) no lo completan y no
            # corresponden a esta sección de "documentos referenciados".
            query_docs = """
                SELECT nombre_documento, tipo_documento, descripcion,
                       DATE_FORMAT(fecha_subida, '%d-%m-%Y %H:%i') as fecha_subida
                FROM documento
                WHERE id_cliente = %s AND estado = 'ACTIVO' AND tipo_documento IS NOT NULL
                ORDER BY fecha_subida DESC
            """
            cursor.execute(query_docs, (id_cliente,))
            cliente["documentos"] = cursor.fetchall()

        return jsonify(cliente), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al obtener ficha consolidada de cliente")
        return jsonify({"error": "Ocurrió una anomalía interna al consolidar los antecedentes del cliente."}), 500

    finally:
        if conexion:
            conexion.close()

# ==========================================================================
# RF06: FILTRANDO CLIENTES POR ÁREA DE SERVICIO Y CRITERIO DE TEXTO (LIKE)
# ==========================================================================
@clientes_blueprint.route('/clientes/filtrar', methods=['GET'])
@roles_required(*ROLES_OPERATIVOS)
def filtrar_clientes_combinado():
    conexion = None
    try:
        # Captura de parámetros opcionales (?id_area=1&buscar=alfa)
        id_area = request.args.get('id_area')
        texto_buscar = request.args.get('buscar', '').strip()
        
        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión con MySQL."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            # Base de la consulta. El LEFT JOIN con área va siempre: además de
            # filtrar por id_area, el texto libre debe poder encontrar
            # coincidencias por nombre de área.
            query = """
                SELECT DISTINCT c.id_cliente, c.rut, c.razon_social, c.telefono, c.estado
                FROM cliente c
                LEFT JOIN cliente_area ca ON c.id_cliente = ca.id_cliente
                LEFT JOIN area a ON ca.id_area = a.id_area
            """
            condiciones = []
            parametros = []

            # Si el usuario seleccionó un departamento, filtramos por esa área
            if id_area:
                condiciones.append("ca.id_area = %s")
                parametros.append(id_area)

            # Si el usuario escribió en el input de texto, agregamos la cláusula LIKE cruzada
            if texto_buscar:
                condiciones.append(
                    "(c.razon_social LIKE %s OR c.rut LIKE %s OR c.email LIKE %s "
                    "OR a.nombre_area LIKE %s OR c.estado LIKE %s)"
                )
                parametro_like = f"%{texto_buscar}%"
                parametros.extend([parametro_like] * 5)

            # Si existen condiciones acumuladas, las inyectamos dinámicamente con un WHERE
            if condiciones:
                query += " WHERE " + " AND ".join(condiciones)
                
            query += " ORDER BY c.razon_social ASC"
            
            cursor.execute(query, tuple(parametros))
            resultados = cursor.fetchall()

        return jsonify(resultados), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al filtrar clientes")
        return jsonify({"error": "Ocurrió una anomalía al procesar el filtrado multi-criterio."}), 500

    finally:
        if conexion:
            conexion.close()


# ==========================================================================
# RF10: CAMBIANDO EL ESTADO DE CLIENTES (ACTIVO <=> INACTIVO) + TRAZABILIDAD
# ==========================================================================
@clientes_blueprint.route('/clientes/<int:id_cliente>/cambiar-estado', methods=['POST'])
@roles_required(ROL_ADMINISTRADOR)
def cambiar_estado_cliente_rf10(id_cliente):
    conexion = None
    try:
        datos = request.json
        nuevo_estado = (datos.get('nuevo_estado') or '').strip().upper()
        id_usuario = obtener_usuario_actual()["id_usuario"]

        if nuevo_estado not in ['ACTIVO', 'INACTIVO']:
            return jsonify({"error": "El estado solicitado no corresponde a un parámetro válido."}), 400

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo interno de comunicación con el motor SQL."}), 500

        with conexion.cursor() as cursor:
            # 1. Rescatar el estado previo para asegurar la trazabilidad del log
            cursor.execute("SELECT estado FROM cliente WHERE id_cliente = %s", (id_cliente,))
            fila = cursor.fetchone()

            if not fila:
                return jsonify({"error": "El cliente especificado no existe."}), 404

            estado_anterior = fila[0]

            if estado_anterior == nuevo_estado:
                return jsonify({"error": f"El cliente ya posee el estado {nuevo_estado} actualmente."}), 400

            # 2. Impactar el nuevo estado en la base de datos
            cursor.execute("UPDATE cliente SET estado = %s WHERE id_cliente = %s", (nuevo_estado, id_cliente))

            # 3. Registrar automáticamente en el historial de la tabla auditoria
            log_anterior = f"estado: {estado_anterior}"
            log_nuevo = f"estado: {nuevo_estado}"
            
            registrar_auditoria(
                cursor, id_usuario, "cliente", "CAMBIO_ESTADO",
                id_registro=id_cliente,
                datos_anteriores=log_anterior,
                datos_nuevos=log_nuevo,
            )
            
            conexion.commit()

        return jsonify({"message": f"Estado actualizado exitosamente a {nuevo_estado}."}), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al cambiar estado de cliente")
        return jsonify({"error": "Error interno al procesar el cambio de estado."}), 500

    finally:
        if conexion:
            conexion.close()


# ==========================================================================
# RF11: LISTANDO GENERALMENTE LOS CLIENTES (CON PAGINACIÓN Y FILTROS CRUZADOS)
# ==========================================================================
def _validar_filtros_listado_clientes():
    id_area = (request.args.get("id_area") or "").strip()
    if id_area == "TODOS":
        id_area = ""
    if id_area and (not id_area.isdecimal() or int(id_area) < 1):
        return None, "id_area debe ser un ID entero positivo."

    id_responsable = (request.args.get("id_responsable") or "").strip()
    if id_responsable and (not id_responsable.isdecimal() or int(id_responsable) < 1):
        return None, "id_responsable debe ser un ID entero positivo."

    estado = (request.args.get("estado") or "").strip().upper()
    if estado and estado not in ("ACTIVO", "INACTIVO"):
        return None, "estado debe ser ACTIVO o INACTIVO."

    return {
        "id_area": id_area,
        "nombre": (request.args.get("nombre") or "").strip(),
        "rut": (request.args.get("rut") or "").strip(),
        "estado": estado,
        "id_responsable": id_responsable,
        "buscar": (request.args.get("buscar") or "").strip(),
    }, None


def _consultar_clientes_listado(cursor, filtros, orden, direccion, limite=None, offset=0):
    query = """
        SELECT DISTINCT c.id_cliente, c.rut, c.razon_social, c.estado, c.telefono,
               c.fecha_creacion,
               (
                   SELECT GROUP_CONCAT(DISTINCT ur.nombres ORDER BY ur.nombres SEPARATOR ' / ')
                   FROM tarea tr_resumen
                   JOIN usuario ur ON tr_resumen.id_responsable = ur.id_usuario
                   WHERE tr_resumen.id_cliente = c.id_cliente
               ) AS responsables_nombres
        FROM cliente c
        LEFT JOIN cliente_area ca ON c.id_cliente = ca.id_cliente
        LEFT JOIN area a ON ca.id_area = a.id_area
    """
    condiciones = []
    parametros = []

    if filtros["id_area"]:
        condiciones.append("ca.id_area = %s")
        parametros.append(filtros["id_area"])
    if filtros["nombre"]:
        condiciones.append("c.razon_social LIKE %s")
        parametros.append(f"%{filtros['nombre']}%")
    if filtros["rut"]:
        condiciones.append("c.rut LIKE %s")
        parametros.append(f"%{filtros['rut']}%")
    if filtros["estado"]:
        condiciones.append("c.estado = %s")
        parametros.append(filtros["estado"])
    if filtros["id_responsable"]:
        condiciones.append(
            "EXISTS (SELECT 1 FROM tarea tr "
            "WHERE tr.id_cliente = c.id_cliente AND tr.id_responsable = %s)"
        )
        parametros.append(filtros["id_responsable"])
    if filtros["buscar"]:
        condiciones.append(
            "(c.razon_social LIKE %s OR c.rut LIKE %s OR c.email LIKE %s "
            "OR a.nombre_area LIKE %s OR c.estado LIKE %s)"
        )
        parametro_like = f"%{filtros['buscar']}%"
        parametros.extend([parametro_like] * 5)

    if condiciones:
        query += " WHERE " + " AND ".join(condiciones)

    columnas_orden = {
        "razon_social": "c.razon_social",
        "estado": "c.estado",
        "fecha_creacion": "c.fecha_creacion",
    }
    direcciones_orden = {"asc": "ASC", "desc": "DESC"}
    query += (
        f" ORDER BY {columnas_orden[orden]} {direcciones_orden[direccion]}, c.id_cliente ASC"
    )
    if limite is not None:
        query += " LIMIT %s OFFSET %s"
        parametros.extend([limite, offset])

    cursor.execute(query, tuple(parametros))
    clientes = cursor.fetchall()
    for cliente in clientes:
        cursor.execute(
            """
            SELECT a.nombre_area FROM cliente_area ca
            JOIN area a ON ca.id_area = a.id_area
            WHERE ca.id_cliente = %s
            """,
            (cliente["id_cliente"],),
        )
        areas = cursor.fetchall()
        nombres = [fila["nombre_area"] for fila in areas]
        cliente["areas_nombres"] = " / ".join(nombres) if nombres else "Sin área"
    return clientes


def _exportar_listado_clientes_excel(clientes):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Clientes"
    hoja.append(["RUT", "Razón Social", "Áreas", "Estado", "Fecha de creación", "Responsables asignados"])

    for cliente in clientes:
        hoja.append([
            cliente["rut"], cliente["razon_social"], cliente["areas_nombres"],
            cliente["estado"], cliente["fecha_creacion"], cliente["responsables_nombres"] or "",
        ])
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
        download_name="clientes_busqueda.xlsx",
    )


@clientes_blueprint.route('/clientes/listado', methods=['GET'])
@roles_required(*ROLES_OPERATIVOS)
def listado_general_paginado_clientes():
    conexion = None
    try:
        # Captura de parámetros de orden y paginación (?pagina=1&limite=7)
        try:
            pagina = int(request.args.get('pagina', 1))
            limite = int(request.args.get('limite', 7))
        except (TypeError, ValueError):
            return jsonify({"error": "Los parámetros de paginación deben ser numéricos."}), 400

        if pagina < 1:
            return jsonify({"error": "El número de página debe ser mayor o igual a 1."}), 400

        # Se acota el límite para evitar consultas arbitrariamente grandes
        # (protección básica ante un límite absurdo enviado por el cliente).
        limite = max(1, min(limite, 100))

        filtros, error = _validar_filtros_listado_clientes()
        if error:
            return jsonify({"error": error}), 400

        formato = (request.args.get("formato") or "").strip().lower()
        if formato not in ("", "excel"):
            return jsonify({"error": "El formato de exportación no es válido."}), 400

        orden = request.args.get('orden', 'razon_social')
        direccion = request.args.get('direccion', 'asc')

        columnas_orden = {
            "razon_social": "c.razon_social",
            "estado": "c.estado",
            "fecha_creacion": "c.fecha_creacion",
        }
        direcciones_orden = {"asc": "ASC", "desc": "DESC"}

        if orden not in columnas_orden:
            return jsonify({"error": "La columna de ordenamiento no es válida."}), 400
        if direccion not in direcciones_orden:
            return jsonify({"error": "La dirección de ordenamiento no es válida."}), 400

        offset = (pagina - 1) * limite

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Error interno de base de datos MySQL."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            clientes = _consultar_clientes_listado(
                cursor, filtros, orden, direccion,
                limite=None if formato == "excel" else limite,
                offset=offset,
            )

        if formato == "excel":
            return _exportar_listado_clientes_excel(clientes), 200

        return jsonify({"clientes": clientes}), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error en listado paginado de clientes")
        return jsonify({"error": "Imposible recuperar la matriz general de clientes."}), 500

    finally:
        if conexion:
            conexion.close()


# ==========================================================================
# RF09: REGISTRANDO Y VISUALIZANDO OBSERVACIONES INTERNAS DE CLIENTES
# ==========================================================================
@clientes_blueprint.route('/clientes/<int:id_cliente>/observaciones', methods=['GET'])
@roles_required(*ROLES_OPERATIVOS)
def listar_observaciones_cliente(id_cliente):
    conexion = None
    try:
        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Error de base de datos."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT id_cliente FROM cliente WHERE id_cliente = %s", (id_cliente,))
            if not cursor.fetchone():
                return jsonify({"error": "Cliente inexistente."}), 404

            cursor.execute("""
                SELECT o.texto, u.nombres AS registrado_por,
                       DATE_FORMAT(o.fecha, '%d-%m-%Y %H:%i') AS fecha
                FROM observacion_cliente o
                INNER JOIN usuario u ON u.id_usuario = o.id_usuario
                WHERE o.id_cliente = %s
                ORDER BY o.fecha DESC
            """, (id_cliente,))
            observaciones = cursor.fetchall()

        return jsonify({"observaciones": observaciones}), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al listar observaciones de cliente")
        return jsonify({"error": "Error interno al obtener las observaciones."}), 500

    finally:
        if conexion:
            conexion.close()


@clientes_blueprint.route('/clientes/<int:id_cliente>/observaciones', methods=['POST'])
@roles_required(*ROLES_OPERATIVOS)
def registrar_observacion_cliente(id_cliente):
    conexion = None
    try:
        datos = request.json or {}
        texto = (datos.get('texto') or '').strip()
        id_usuario = obtener_usuario_actual()["id_usuario"]

        if not texto:
            return jsonify({"error": "El texto de la observación es obligatorio."}), 400

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Error de base de datos."}), 500

        with conexion.cursor() as cursor:
            cursor.execute("SELECT id_cliente FROM cliente WHERE id_cliente = %s", (id_cliente,))
            if not cursor.fetchone():
                return jsonify({"error": "Cliente inexistente."}), 404

            cursor.execute("""
                INSERT INTO observacion_cliente (id_cliente, id_usuario, texto)
                VALUES (%s, %s, %s)
            """, (id_cliente, id_usuario, texto))

            conexion.commit()

        return jsonify({"message": "Observación registrada correctamente."}), 201

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error al registrar observación de cliente")
        return jsonify({"error": "Error interno al registrar la observación."}), 500

    finally:
        if conexion:
            conexion.close()


@clientes_blueprint.route('/clientes/resumen', methods=['GET'])
@roles_required(*ROLES_OPERATIVOS)
def resumen_clientes_dashboard():
    conexion = None
    try:
        conexion = get_connection()

        if conexion is None:
            return jsonify({"error": "Error interno de base de datos MySQL."}), 500

        with conexion.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM cliente")
            total_clientes = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) AS total FROM cliente WHERE estado = 'ACTIVO'")
            clientes_activos = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) AS total FROM cliente WHERE estado = 'INACTIVO'")
            clientes_inactivos = cursor.fetchone()["total"]

            query_ultimos = """
                SELECT id_cliente, rut, razon_social, email, telefono, estado
                FROM cliente
                ORDER BY fecha_creacion DESC
                LIMIT 5
            """
            cursor.execute(query_ultimos)
            ultimos_clientes = cursor.fetchall()

        return jsonify({
            "total_clientes": total_clientes,
            "clientes_activos": clientes_activos,
            "clientes_inactivos": clientes_inactivos,
            "ultimos_clientes": ultimos_clientes
        }), 200

    except Exception:
        if conexion:
            conexion.rollback()
        logger.exception("Error en resumen de clientes para dashboard")
        return jsonify({"error": "No se pudo cargar el resumen de clientes."}), 500

    finally:
        if conexion:
            conexion.close()
@clientes_blueprint.route('/clientes/<int:id_cliente>/historial-completo', methods=['GET'])
@roles_required(*ROLES_OPERATIVOS)
def historial_cliente(id_cliente):
    conexion = None
    cursor = None
    try:
        limite = request.args.get('limite', default=50, type=int)
        offset = request.args.get('offset', default=0, type=int)
        accion = (request.args.get('accion') or '').strip()
        fecha = (request.args.get('fecha') or '').strip()

        if limite is None or limite < 0:
            limite = 50
        if offset is None or offset < 0:
            offset = 0

        if fecha:
            try:
                fecha_dt = datetime.strptime(fecha, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"error": "La fecha debe tener el formato AAAA-MM-DD."}), 400
            fecha_inicio = fecha_dt.isoformat()
            fecha_fin = fecha_dt.isoformat()
        else:
            fecha_inicio = request.args.get('fecha_inicio')
            fecha_fin = request.args.get('fecha_fin')

        conexion = get_connection()
        if conexion is None:
            return jsonify({"error": "Fallo de conexión."}), 500

        cursor = conexion.cursor(dictionary=True)

        cursor.execute("SELECT id_cliente FROM cliente WHERE id_cliente = %s", (id_cliente,))
        if not cursor.fetchone():
            return jsonify({"error": "Cliente inexistente."}), 404

        cursor.execute(
            "SELECT id_observacion FROM observacion_cliente WHERE id_cliente = %s",
            (id_cliente,)
        )
        ids_observaciones = [row["id_observacion"] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT id_tarea FROM tarea WHERE id_cliente = %s",
            (id_cliente,)
        )
        ids_tareas = [row["id_tarea"] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT id_documento FROM documento WHERE id_cliente = %s",
            (id_cliente,)
        )
        ids_documentos = [row["id_documento"] for row in cursor.fetchall()]

        lista_registros = [("cliente", id_cliente)]
        for id_obs in ids_observaciones:
            lista_registros.append(("observacion_cliente", id_obs))
        for id_tarea in ids_tareas:
            lista_registros.append(("tarea", id_tarea))
        for id_doc in ids_documentos:
            lista_registros.append(("documento", id_doc))

        filtros = {
            "registros": lista_registros,
            "limite": limite,
            "offset": offset,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
        }
        if accion:
            filtros["acciones"] = [accion]

        filas, total = consultar_auditoria(cursor, **filtros)

        for fila in filas:
            fecha_value = fila.get('fecha')
            if fecha_value:
                try:
                    fecha_dt = datetime.strptime(str(fecha_value), '%Y-%m-%d %H:%M:%S')
                    fila['fecha'] = fecha_dt.date().isoformat()
                    fila['hora'] = fecha_dt.time().strftime('%H:%M:%S')
                except ValueError:
                    fila['fecha'] = str(fecha_value).split(' ')[0] if ' ' in str(fecha_value) else str(fecha_value)
                    fila['hora'] = str(fecha_value).split(' ')[1] if ' ' in str(fecha_value) else '00:00:00'
            if not fila.get('usuario'):
                fila['usuario'] = 'Sistema'

        return jsonify({
            "historial": filas,
            "total": total
        }), 200

    except Exception:
        logger.exception("Error al consultar historial del cliente")
        return jsonify({"error": "Error interno del servidor."}), 500

    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None:
            conexion.close()