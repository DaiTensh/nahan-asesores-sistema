"""Registro y consulta de la tabla AUDITORIA (Incremento 3).

Es la interfaz compartida del Incremento 3: la usan RF56 (historial global),
RF40 (historial consolidado), RF13 (historial por cliente), RF30 (historial
por usuario), RF59 (cierre por inactividad) y RF76 (revisión de tareas).
Ninguna ruta debe escribir `INSERT INTO auditoria` a mano: así todas las
filas quedan con el mismo formato y con `id_registro`, que es lo que permite
consultar el historial de un registro sin interpretar el texto libre.
"""
from datetime import date, datetime, timedelta

# Módulo funcional al que pertenece cada tabla auditada. Se usa para mostrar
# y filtrar el historial por módulo (RF56: «acción, módulo, usuario, fecha y
# hora»). Una tabla nueva que empiece a auditarse debe agregarse aquí.
MODULO_POR_TABLA = {
    "cliente": "Clientes",
    "observacion_cliente": "Clientes",
    "documento": "Documentos",
    "tarea": "Tareas",
    "revision_tarea": "Tareas",
    "usuario": "Usuarios",
    "sesion": "Seguridad",
    "token_recuperacion": "Seguridad",
    "reporte": "Reportes",
    "parametros_sistema": "Configuración",
}

MODULO_DESCONOCIDO = "Otros"


def modulo_de_tabla(tabla_afectada):
    return MODULO_POR_TABLA.get(tabla_afectada, MODULO_DESCONOCIDO)


def modulos_disponibles():
    return sorted(set(MODULO_POR_TABLA.values()))


def tablas_de_modulo(modulo):
    """Tablas que pertenecen a `modulo`, o lista vacía si el módulo no existe."""
    return sorted(tabla for tabla, nombre in MODULO_POR_TABLA.items() if nombre == modulo)


def registrar_auditoria(cursor, id_usuario, tabla_afectada, accion,
                        id_registro=None, datos_anteriores=None, datos_nuevos=None):
    """Inserta un evento en AUDITORIA.

    No hace commit: el evento debe quedar dentro de la misma transacción que
    la operación que registra, de modo que si esa operación hace rollback el
    evento tampoco quede escrito.
    """
    cursor.execute(
        """
        INSERT INTO auditoria
            (id_usuario, tabla_afectada, id_registro, accion, datos_anteriores, datos_nuevos)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (id_usuario, tabla_afectada, id_registro, accion, datos_anteriores, datos_nuevos),
    )


def _condicion_registros(registros):
    """Arma la condición SQL de una lista de pares (tabla, id_registro).

    Devuelve (condicion, parametros), o (None, []) si la lista está vacía.
    """
    por_tabla = {}
    for tabla, id_registro in registros:
        por_tabla.setdefault(tabla, []).append(id_registro)
    if not por_tabla:
        return None, []

    partes = []
    parametros = []
    for tabla, ids in por_tabla.items():
        partes.append(
            f"(a.tabla_afectada = %s AND a.id_registro IN ({', '.join(['%s'] * len(ids))}))"
        )
        parametros.append(tabla)
        parametros.extend(ids)
    return "(" + " OR ".join(partes) + ")", parametros


def acciones_de_registros(cursor, registros):
    """Acciones distintas registradas sobre `registros`, en orden alfabético.

    La usa RF13 para ofrecer el filtro por tipo de acción solo con las
    acciones que existen en el historial del cliente. Acepta cursores con o
    sin dictionary=True.
    """
    condicion, parametros = _condicion_registros(registros)
    if condicion is None:
        return []

    cursor.execute(
        f"SELECT DISTINCT a.accion AS accion FROM auditoria a WHERE {condicion} ORDER BY a.accion",
        tuple(parametros),
    )
    return [fila["accion"] if isinstance(fila, dict) else fila[0] for fila in cursor.fetchall()]


def _dia_siguiente(fecha_iso):
    return (date.fromisoformat(fecha_iso) + timedelta(days=1)).isoformat()


def _formatear_fecha(valor):
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    return str(valor) if valor is not None else None


def consultar_auditoria(cursor, *, id_usuario=None, tablas=None, acciones=None,
                        registros=None, fecha_inicio=None, fecha_fin=None,
                        limite=50, offset=0):
    """Consulta AUDITORIA con filtros opcionales combinados con AND.

    - id_usuario: usuario que ejecutó la acción.
    - tablas: lista de tablas (p. ej. tablas_de_modulo("Tareas")).
    - acciones: lista de acciones (p. ej. ["LOGIN", "LOGOUT"]).
    - registros: lista de pares (tabla, id_registro); un evento coincide si
      pertenece a cualquiera de esos registros. La usa RF13 para armar el
      historial de un cliente con sus tareas, documentos y observaciones.
    - fecha_inicio / fecha_fin: 'AAAA-MM-DD', ambos inclusive (validarlos
      antes, p. ej. con reportes_routes._validar_periodo).
    - limite: None para traer todo (RF40); offset para paginar.

    Requiere un cursor con dictionary=True. Devuelve (filas, total), en orden
    cronológico descendente. Cada fila trae además la clave `modulo`.
    """
    condiciones = []
    parametros = []

    if id_usuario is not None:
        condiciones.append("a.id_usuario = %s")
        parametros.append(id_usuario)

    if tablas is not None:
        if not tablas:
            return [], 0
        condiciones.append(f"a.tabla_afectada IN ({', '.join(['%s'] * len(tablas))})")
        parametros.extend(tablas)

    if acciones is not None:
        if not acciones:
            return [], 0
        condiciones.append(f"a.accion IN ({', '.join(['%s'] * len(acciones))})")
        parametros.extend(acciones)

    if registros is not None:
        condicion, parametros_registros = _condicion_registros(registros)
        if condicion is None:
            return [], 0
        condiciones.append(condicion)
        parametros.extend(parametros_registros)

    if fecha_inicio:
        condiciones.append("a.fecha >= %s")
        parametros.append(fecha_inicio)

    if fecha_fin:
        condiciones.append("a.fecha < %s")
        parametros.append(_dia_siguiente(fecha_fin))

    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

    cursor.execute(f"SELECT COUNT(*) AS total FROM auditoria a {where}", tuple(parametros))
    fila_total = cursor.fetchone() or {}
    total = int(fila_total.get("total") or 0)

    consulta = f"""
        SELECT a.id_auditoria, a.fecha, a.id_usuario, u.nombres AS usuario,
               a.tabla_afectada, a.id_registro, a.accion,
               a.datos_anteriores, a.datos_nuevos
        FROM auditoria a
        LEFT JOIN usuario u ON u.id_usuario = a.id_usuario
        {where}
        ORDER BY a.fecha DESC, a.id_auditoria DESC
    """
    parametros_consulta = list(parametros)
    if limite is not None:
        consulta += " LIMIT %s OFFSET %s"
        parametros_consulta.extend([int(limite), int(offset or 0)])

    cursor.execute(consulta, tuple(parametros_consulta))
    filas = []
    for fila in cursor.fetchall():
        fila = dict(fila)
        fila["fecha"] = _formatear_fecha(fila.get("fecha"))
        fila["modulo"] = modulo_de_tabla(fila.get("tabla_afectada"))
        filas.append(fila)

    return filas, total
