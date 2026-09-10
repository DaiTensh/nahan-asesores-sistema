#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Datos de desarrollo para Nahan Asesores.

Crea los siete usuarios del equipo, clientes de ejemplo, tareas en todos los
estados posibles y algunos registros de tiempo, de modo que una instalación
recién hecha se pueda usar y capturar de inmediato.

Es idempotente: se puede ejecutar las veces que haga falta. Detecta lo que ya
existe por su clave natural (email o RUT) y no lo duplica.

    python database/seed_dev.py            # siembra
    python database/seed_dev.py --reset    # borra lo sembrado y vuelve a sembrar

NO usar en producción: las contraseñas son públicas y están en este archivo.
"""
import argparse
import os
import sys
from datetime import date, datetime, time, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

try:
    from backend.config.db import get_connection
    from backend.utils.security import hash_password
except ImportError as e:                                     # pragma: no cover
    print(f"No se pudieron importar los módulos del backend: {e}")
    print("Ejecuta el script desde la raíz del repositorio y con el entorno virtual activado.")
    sys.exit(1)

# La misma para todos, a propósito: es una base local de desarrollo y tiene que
# poder escribirse en la pizarra sin que nadie tenga que preguntarla.
PASSWORD_DEV = "Nahan.2026"

# (nombres, email, rol, area)
USUARIOS = [
    ("Renato Villalobos",  "renato.villalobos@nahan.local",  "ADMINISTRADOR",          "ADMINISTRACION"),
    ("Matías Rodríguez",   "matias.rodriguez@nahan.local",   "ADMINISTRADOR",          "ADMINISTRACION"),
    ("Benjamín Contreras", "benjamin.contreras@nahan.local", "ADMINISTRADOR",          "ADMINISTRACION"),
    ("Elías Alarcón",      "elias.alarcon@nahan.local",      "USUARIO_AREA_JURIDICA",  "JURIDICA"),
    ("Vicente Barahona",   "vicente.barahona@nahan.local",   "USUARIO_AREA_JURIDICA",  "JURIDICA"),
    ("Carlos Castro",      "carlos.castro@nahan.local",      "USUARIO_AREA_CONTABLE",  "CONTABLE"),
    ("Iván Gómez",         "ivan.gomez@nahan.local",         "USUARIO_AREA_CONTABLE",  "CONTABLE"),
]

# (rut, razon_social, email, telefono, direccion, estado, area)
CLIENTES = [
    ("76.543.210-9", "Comercial Andes SpA",            "contacto@comercialandes.cl",  "+56 2 2345 6789", "Av. Providencia 1234, Santiago",  "ACTIVO",   "JURIDICA"),
    ("77.812.455-1", "Constructora Los Robles Ltda.",  "admin@losrobles.cl",          "+56 2 2987 1122", "Av. Vitacura 4321, Santiago",     "ACTIVO",   "JURIDICA"),
    ("78.220.876-K", "Importadora del Pacífico SpA",   "gerencia@impacifico.cl",      "+56 2 2456 7788", "Nueva Costanera 890, Santiago",   "ACTIVO",   "CONTABLE"),
    ("79.004.331-5", "Agrícola Valle Verde Ltda.",     "contabilidad@valleverde.cl",  "+56 72 234 5566", "Camino El Roble s/n, Rancagua",   "ACTIVO",   "CONTABLE"),
    ("80.115.998-3", "Servicios Australes SpA",        "contacto@australes.cl",       "+56 61 222 3344", "Bories 456, Punta Arenas",        "ACTIVO",   "JURIDICA"),
    ("81.667.220-7", "Transportes Cordillera Ltda.",   "operaciones@tcordillera.cl",  "+56 2 2777 8899", "Camino a Melipilla 9100, Maipú",  "INACTIVO", "CONTABLE"),
]

# (cliente_rut, titulo, descripcion, estado, prioridad, dias_vencimiento, responsable_email, area)
# dias_vencimiento es relativo a hoy: negativo = vencida.
TAREAS = [
    ("76.543.210-9", "Revisión de contrato de arriendo comercial",
     "Revisar cláusulas de renovación automática y multa por término anticipado.",
     "PENDIENTE",   "ALTA",    5,   "elias.alarcon@nahan.local",     "JURIDICA"),
    ("76.543.210-9", "Constitución de sociedad filial",
     "Redactar estatutos y coordinar firma ante notario.",
     "EN_PROCESO",  "MEDIA",   12,  "vicente.barahona@nahan.local",  "JURIDICA"),
    ("77.812.455-1", "Defensa en reclamo de la Dirección del Trabajo",
     "Preparar descargos y reunir antecedentes del contrato de obra.",
     "EN_PROCESO",  "URGENTE", -3,  "elias.alarcon@nahan.local",     "JURIDICA"),
    ("77.812.455-1", "Inscripción de marca comercial",
     "Presentar solicitud ante INAPI y hacer seguimiento de la publicación.",
     "EN_REVISION", "MEDIA",   8,   "vicente.barahona@nahan.local",  "JURIDICA"),
    ("78.220.876-K", "Declaración mensual de IVA",
     "Consolidar libros de compra y venta del período y presentar el F29.",
     "COMPLETADA",  "ALTA",    -10, "carlos.castro@nahan.local",     "CONTABLE"),
    ("78.220.876-K", "Conciliación bancaria del trimestre",
     "Cuadrar cartolas contra el libro mayor y documentar las diferencias.",
     "PENDIENTE",   "MEDIA",   3,   "ivan.gomez@nahan.local",        "CONTABLE"),
    ("79.004.331-5", "Cierre contable anual",
     "Preparar balance de ocho columnas y estado de resultados.",
     "EN_PROCESO",  "ALTA",    20,  "carlos.castro@nahan.local",     "CONTABLE"),
    ("79.004.331-5", "Regularización de facturas rechazadas",
     "Revisar el rechazo del SII y reemitir los documentos observados.",
     "PENDIENTE",   "URGENTE", -1,  "ivan.gomez@nahan.local",        "CONTABLE"),
    ("80.115.998-3", "Redacción de pacto de accionistas",
     "Incorporar cláusula de arrastre y derecho preferente de compra.",
     "PENDIENTE",   "BAJA",    30,  "vicente.barahona@nahan.local",  "JURIDICA"),
    ("80.115.998-3", "Actualización de poderes ante el banco",
     "Reunir la documentación societaria vigente y presentarla.",
     "CANCELADA",   "BAJA",    15,  "elias.alarcon@nahan.local",     "JURIDICA"),
    ("81.667.220-7", "Revisión de contrato de transporte",
     "Verificar cobertura de seguro de carga y responsabilidad del porteador.",
     "COMPLETADA",  "MEDIA",   -25, "carlos.castro@nahan.local",     "CONTABLE"),
    ("76.543.210-9", "Informe tributario para la junta de accionistas",
     "Consolidar la carga tributaria del ejercicio y proyectar el siguiente.",
     "EN_REVISION", "ALTA",    2,   "ivan.gomez@nahan.local",        "CONTABLE"),
]

TARIFAS = [("JURIDICA", 45000), ("CONTABLE", 38000), ("ADMINISTRACION", 30000)]


# ---------------------------------------------------------------- utilidades
class Sembrador:
    def __init__(self, cursor):
        self.c = cursor
        self.creado = {}
        self.omitido = {}

    def _contar(self, mapa, clave):
        mapa[clave] = mapa.get(clave, 0) + 1

    def uno(self, sql, params=()):
        self.c.execute(sql, params)
        fila = self.c.fetchone()
        return fila[0] if fila else None

    def insertar(self, tabla, sql, params, existe_sql, existe_params):
        """Inserta solo si la clave natural no está. Devuelve el id en ambos casos."""
        existente = self.uno(existe_sql, existe_params)
        if existente is not None:
            self._contar(self.omitido, tabla)
            return existente
        self.c.execute(sql, params)
        self._contar(self.creado, tabla)
        return self.c.lastrowid


def resumen(titulo, mapa):
    if not mapa:
        return
    detalle = ", ".join(f"{v} en {k}" for k, v in sorted(mapa.items()))
    print(f"  {titulo}: {detalle}")


# --------------------------------------------------------------------- reset
# (tabla, sql, ¿lleva la lista de RUT como parámetros?) — en orden hijo → padre.
LIMPIEZA = [
    ("registro_tiempo", "DELETE FROM registro_tiempo WHERE id_usuario IN "
                        "(SELECT id_usuario FROM usuario WHERE email LIKE '%@nahan.local')", False),
    ("notificacion",    "DELETE FROM notificacion WHERE id_usuario IN "
                        "(SELECT id_usuario FROM usuario WHERE email LIKE '%@nahan.local')", False),
    ("reporte",         "DELETE FROM reporte WHERE id_usuario IN "
                        "(SELECT id_usuario FROM usuario WHERE email LIKE '%@nahan.local')", False),
    ("auditoria",       "DELETE FROM auditoria WHERE id_usuario IN "
                        "(SELECT id_usuario FROM usuario WHERE email LIKE '%@nahan.local')", False),
    ("tarea",           "DELETE FROM tarea WHERE id_cliente IN "
                        "(SELECT id_cliente FROM cliente WHERE rut IN ({ruts}))", True),
    ("cliente_area",    "DELETE FROM cliente_area WHERE id_cliente IN "
                        "(SELECT id_cliente FROM cliente WHERE rut IN ({ruts}))", True),
    ("cliente",         "DELETE FROM cliente WHERE rut IN ({ruts})", True),
    ("usuario",         "DELETE FROM usuario WHERE email LIKE '%@nahan.local'", False),
]


def limpiar(cursor):
    ruts = [c[0] for c in CLIENTES]
    marcas = ", ".join(["%s"] * len(ruts))
    print("Borrando los datos de desarrollo anteriores...")
    for tabla, plantilla, lleva_ruts in LIMPIEZA:
        sql = plantilla.format(ruts=marcas) if lleva_ruts else plantilla
        cursor.execute(sql, tuple(ruts) if lleva_ruts else ())
        if cursor.rowcount:
            print(f"  {tabla}: {cursor.rowcount} fila(s)")


# ------------------------------------------------------------------- siembra
def sembrar(cursor):
    s = Sembrador(cursor)

    roles = {}
    cursor.execute("SELECT nombre_rol, id_rol FROM rol")
    roles = dict(cursor.fetchall())
    areas = {}
    cursor.execute("SELECT nombre_area, id_area FROM area")
    areas = dict(cursor.fetchall())

    faltan = [r for _, _, r, _ in USUARIOS if r not in roles] + [a for _, _, _, a in USUARIOS if a not in areas]
    if faltan:
        raise SystemExit(
            "La base no tiene los roles y áreas base: falta " + ", ".join(sorted(set(faltan))) +
            ".\nImporta primero database/nahan_asesores.sql."
        )

    # --- usuarios ---
    hash_dev = hash_password(PASSWORD_DEV)
    ids_usuario = {}
    for nombres, email, rol, area in USUARIOS:
        ids_usuario[email] = s.insertar(
            "usuario",
            "INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash, estado) "
            "VALUES (%s, %s, %s, %s, %s, 'ACTIVO')",
            (roles[rol], areas[area], nombres, email, hash_dev),
            "SELECT id_usuario FROM usuario WHERE email = %s", (email,),
        )
    admin = ids_usuario["renato.villalobos@nahan.local"]

    # --- tarifas por área ---
    for area, valor in TARIFAS:
        s.insertar(
            "tarifa_hora",
            "INSERT INTO tarifa_hora (id_area, valor_hora, moneda, fecha_inicio, descripcion, estado) "
            "VALUES (%s, %s, 'CLP', %s, %s, 'ACTIVA')",
            (areas[area], valor, date(2026, 1, 1), f"Tarifa vigente del área {area.lower()}"),
            "SELECT id_tarifa FROM tarifa_hora WHERE id_area = %s AND estado = 'ACTIVA'", (areas[area],),
        )

    # --- clientes ---
    ids_cliente = {}
    for rut, razon, email, tel, dir_, estado, area in CLIENTES:
        ids_cliente[rut] = s.insertar(
            "cliente",
            "INSERT INTO cliente (rut, razon_social, email, telefono, direccion, estado) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (rut, razon, email, tel, dir_, estado),
            "SELECT id_cliente FROM cliente WHERE rut = %s", (rut,),
        )
        s.insertar(
            "cliente_area",
            "INSERT INTO cliente_area (id_cliente, id_area, fecha_asignacion) VALUES (%s, %s, %s)",
            (ids_cliente[rut], areas[area], date(2026, 1, 15)),
            "SELECT id_cliente_area FROM cliente_area WHERE id_cliente = %s AND id_area = %s",
            (ids_cliente[rut], areas[area]),
        )

    # --- tareas ---
    hoy = date.today()
    ids_tarea = {}
    for rut, titulo, desc, estado, prio, dias, resp, area in TAREAS:
        vence = hoy + timedelta(days=dias)
        inicio = None if estado == "PENDIENTE" else datetime.combine(vence - timedelta(days=10), time(9, 0))
        fin = datetime.combine(vence, time(17, 30)) if estado == "COMPLETADA" else None
        # Para las tareas ya completadas, fecha_creacion debe quedar antes de
        # fin; si se deja en el valor por defecto (CURRENT_TIMESTAMP, o sea el
        # instante de la siembra) queda después de `fin` cuando `vence` cae en
        # el pasado, y el tiempo de resolución de RF39 sale negativo.
        creacion = datetime.combine(vence - timedelta(days=15), time(9, 0)) if estado == "COMPLETADA" else datetime.now()
        ids_tarea[titulo] = s.insertar(
            "tarea",
            "INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, descripcion, "
            "estado, prioridad, fecha_creacion, fecha_vencimiento, fecha_inicio, fecha_finalizacion) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (ids_cliente[rut], areas[area], ids_usuario[resp], admin, titulo, desc,
             estado, prio, creacion, vence, inicio, fin),
            "SELECT id_tarea FROM tarea WHERE titulo = %s AND id_cliente = %s",
            (titulo, ids_cliente[rut]),
        )

    # --- registros de tiempo sobre tareas ya trabajadas ---
    trabajadas = [t for t in TAREAS if t[3] in ("EN_PROCESO", "COMPLETADA", "EN_REVISION")]
    for i, (rut, titulo, _, _, _, _, resp, area) in enumerate(trabajadas):
        tarifa = dict(TARIFAS)[area]
        fecha = hoy - timedelta(days=i + 1)
        minutos = 60 * (2 + (i % 3))
        s.insertar(
            "registro_tiempo",
            "INSERT INTO registro_tiempo (id_usuario, id_cliente, id_tarea, fecha, hora_inicio, hora_fin, "
            "duracion_minutos, tarifa_hora) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (ids_usuario[resp], ids_cliente[rut], ids_tarea[titulo], fecha,
             time(9, 0), time(9 + minutos // 60, 0), minutos, tarifa),
            "SELECT id_registro FROM registro_tiempo WHERE id_tarea = %s AND fecha = %s",
            (ids_tarea[titulo], fecha),
        )

    return s


def main():
    ap = argparse.ArgumentParser(description="Siembra los datos de desarrollo de Nahan Asesores.")
    ap.add_argument("--reset", action="store_true",
                    help="borra los datos de desarrollo anteriores antes de sembrar")
    args = ap.parse_args()

    conexion = get_connection()
    if conexion is None:
        print("No hay conexión con MySQL. Revisa el archivo .env y que el servidor esté corriendo.")
        print("Diagnóstico: python scripts/doctor.py")
        return 1

    cursor = conexion.cursor()
    try:
        if args.reset:
            limpiar(cursor)
        s = sembrar(cursor)
        conexion.commit()
    except Exception as e:
        conexion.rollback()
        print(f"La siembra falló y se revirtió por completo: {e}")
        return 1
    finally:
        cursor.close()
        conexion.close()

    print("Datos de desarrollo listos.")
    resumen("Creado", s.creado)
    resumen("Ya existía", s.omitido)
    print()
    print(f"  Contraseña de todos los usuarios: {PASSWORD_DEV}")
    print("  Administrador: renato.villalobos@nahan.local")
    print("  Área jurídica: elias.alarcon@nahan.local")
    print("  Área contable: carlos.castro@nahan.local")
    return 0


if __name__ == "__main__":
    sys.exit(main())
