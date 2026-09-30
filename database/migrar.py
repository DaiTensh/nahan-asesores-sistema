#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplica a una base existente las migraciones de database/migraciones/ que le
falten, en orden, sin borrar ni recrear nada.

Una base importada desde cero con database/nahan_asesores.sql ya trae todas
las migraciones; una base creada en un incremento anterior no. Este script
revisa cada migración contra el estado real de la base (tablas, columnas,
índices y parámetros) y ejecuta solo las que faltan. Se puede repetir las
veces que haga falta: lo ya aplicado se omite.

    .venv/bin/python database/migrar.py              # aplica lo pendiente
    .venv/bin/python database/migrar.py --comprobar  # solo informa; sale con 1 si falta algo

    .venv\\Scripts\\python.exe database\\migrar.py      # Windows

Lo ejecuta scripts/setup.py en cada instalación. Usa la conexión de .env
(DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME).

Para agregar una migración nueva: crear database/migraciones/NNN_nombre.sql
y, si es posible, registrar en MARCADORES cómo se reconoce que ya está
aplicada. Sin marcador, la migración se ejecuta en cada corrida y solo se
toleran los errores de «ya existe» (tabla, columna, índice o clave foránea).
"""
import argparse
import glob
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(RAIZ, "database", "migraciones")
ES_WINDOWS = os.name == "nt"
CMD_SETUP = (r"powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"
             if ES_WINDOWS else "bash scripts/setup.sh")
CMD_DOCTOR = (r"powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1"
              if ES_WINDOWS else "bash scripts/doctor.sh")

# Errores de MySQL que significan «esto ya estaba aplicado».
YA_EXISTE = {
    1050,  # la tabla ya existe
    1060,  # la columna ya existe
    1061,  # el índice ya existe
    1826,  # la clave foránea ya existe
}

# Cómo se reconoce en la base que cada migración ya está aplicada.
# Cada entrada es una lista de (consulta, parámetros); la migración se
# considera aplicada si todas devuelven un conteo mayor que cero.
_TABLA = ("SELECT COUNT(*) FROM information_schema.tables "
          "WHERE table_schema = DATABASE() AND table_name = %s")
_COLUMNA = ("SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s")
_INDICE = ("SELECT COUNT(*) FROM information_schema.statistics "
           "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s")
_PARAMETRO = "SELECT COUNT(*) FROM parametros_sistema WHERE nombre_parametro = %s"

MARCADORES = {
    "001": [(_TABLA, ("token_recuperacion",))],
    "002": [(_PARAMETRO, ("ADJUNTOS_TAMANO_MAXIMO_MB",)),
            (_PARAMETRO, ("ADJUNTOS_EXTENSIONES_PERMITIDAS",))],
    "003": [(_COLUMNA, ("documento", "tipo_documento")),
            (_INDICE, ("documento", "uq_documento_referencia"))],
    "004": [(_TABLA, ("observacion_cliente",))],
    "005": [(_COLUMNA, ("auditoria", "id_registro")),
            (_INDICE, ("auditoria", "idx_auditoria_tabla_registro")),
            (_INDICE, ("auditoria", "idx_auditoria_usuario_fecha")),
            (_INDICE, ("auditoria", "idx_auditoria_fecha"))],
    "006": [(_PARAMETRO, ("SESION_INACTIVIDAD_MINUTOS",)),
            (_PARAMETRO, ("SESION_AVISO_SEGUNDOS",))],
    "007": [(_COLUMNA, ("notificacion", "importancia"))],
}


def migraciones():
    """[(numero, nombre_de_archivo, ruta)] en orden."""
    lista = []
    for ruta in sorted(glob.glob(os.path.join(CARPETA, "*.sql"))):
        nombre = os.path.basename(ruta)
        m = re.match(r"(\d{3})_", nombre)
        if m:
            lista.append((m.group(1), nombre, ruta))
    return lista


def sentencias(ruta):
    """Las sentencias del archivo, sin los comentarios de línea."""
    texto = open(ruta, encoding="utf-8").read()
    sin_comentarios = "\n".join(l for l in texto.splitlines() if not l.strip().startswith("--"))
    return [s.strip() for s in sin_comentarios.split(";") if s.strip()]


def aplicada(cur, numero):
    """True / False según los marcadores; None si la migración no tiene marcador."""
    if numero not in MARCADORES:
        return None
    for consulta, params in MARCADORES[numero]:
        cur.execute(consulta, params)
        if not cur.fetchone()[0]:
            return False
    return True


def pendientes(cur):
    """Números de las migraciones con marcador que todavía no están aplicadas."""
    return [n for n, _, _ in migraciones() if aplicada(cur, n) is False]


def aplicar(cn, ruta):
    """Ejecuta una migración. Devuelve cuántas sentencias se omitieron por «ya existe»."""
    import mysql.connector
    cur = cn.cursor()
    omitidas = 0
    try:
        for s in sentencias(ruta):
            try:
                cur.execute(s)
                while cur.nextset():
                    pass
            except mysql.connector.Error as e:
                if e.errno in YA_EXISTE:
                    omitidas += 1
                    continue
                raise
        cn.commit()
    finally:
        cur.close()
    return omitidas


def conectar():
    try:
        import mysql.connector
        from dotenv import load_dotenv
    except ImportError as e:
        print(f"Falta una dependencia ({e.name}). Ejecuta primero el instalador: {CMD_SETUP}")
        sys.exit(1)
    load_dotenv(os.path.join(RAIZ, ".env"))
    base = os.getenv("DB_NAME", "nahan_asesores")
    try:
        cn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", ""), password=os.getenv("DB_PASSWORD", ""),
            database=base, connection_timeout=6)
    except mysql.connector.Error as e:
        print(f"No se pudo conectar con la base «{base}»: {e}")
        if e.errno == 1049:
            print(f"La base no existe. Créala con el instalador: {CMD_SETUP}")
        else:
            print(f"Revisa que MySQL esté corriendo y los datos de .env. Diagnóstico: {CMD_DOCTOR}")
        sys.exit(1)
    return cn, base


def main():
    ap = argparse.ArgumentParser(description="Aplica las migraciones pendientes a la base local.")
    ap.add_argument("--comprobar", action="store_true",
                    help="solo informa qué migraciones faltan; no modifica la base")
    args = ap.parse_args()

    cn, base = conectar()
    cur = cn.cursor()
    faltan = 0
    try:
        for numero, nombre, ruta in migraciones():
            estado = aplicada(cur, numero)
            if estado:
                print(f"  {nombre}: ya aplicada")
                continue
            if args.comprobar:
                if estado is False:
                    faltan += 1
                    print(f"  {nombre}: PENDIENTE")
                else:
                    print(f"  {nombre}: sin marcador, no se puede comprobar")
                continue
            try:
                omitidas = aplicar(cn, ruta)
            except Exception as e:
                print(f"  {nombre}: FALLÓ — {e}")
                print("  La base no se borró. Corrige el problema y vuelve a ejecutar este script.")
                return 1
            if aplicada(cur, numero) is False:
                print(f"  {nombre}: se ejecutó, pero la base sigue sin reflejarla")
                return 1
            print(f"  {nombre}: aplicada" + (f" ({omitidas} sentencia(s) ya existían)" if omitidas else ""))
    finally:
        cur.close()
        cn.close()

    if args.comprobar and faltan:
        print(f"Faltan {faltan} migración(es) en «{base}». Aplícalas con el instalador: {CMD_SETUP}")
        return 1
    print(f"Base «{base}» al día con database/migraciones/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
