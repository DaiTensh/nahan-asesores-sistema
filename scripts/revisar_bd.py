#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Revisa qué dejó en la base la suite de pruebas antes de que se aislara.

Hasta el arreglo del conftest, `tests/test_incremento1_regression.py` alcanzaba
el MySQL local a través del decorador de autorización y llegaba a escribir en
él. Este script busca ese rastro y, con --limpiar, borra la parte que no admite
duda: los usuarios con correo @nahan.test, que no existen en ningún dato de
demo y solo puede haberlos creado una prueba.

Lo demás —un cliente deshabilitado, filas de auditoría— se informa pero no se
toca: no hay forma de saber desde aquí si venía así de antes.

    .venv/bin/python scripts/revisar_bd.py
    .venv/bin/python scripts/revisar_bd.py --limpiar
    .venv/bin/python scripts/revisar_bd.py --salida informe_bd.txt
"""
import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORREO_DE_PRUEBAS = "%@nahan.test"


class Salida:
    """Escribe a la pantalla y, si se pidió, también a un archivo."""

    def __init__(self, ruta=None):
        self.lineas = []
        self.ruta = ruta

    def __call__(self, texto=""):
        print(texto)
        self.lineas.append(texto)

    def guardar(self):
        if not self.ruta:
            return
        with open(self.ruta, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lineas) + "\n")


def conectar():
    try:
        import mysql.connector
        from dotenv import load_dotenv
    except ImportError as e:
        print(f"Falta una dependencia ({e.name}). Ejecuta: bash scripts/setup.sh --solo-deps")
        sys.exit(1)

    load_dotenv(os.path.join(RAIZ, ".env"))
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "nahan_asesores"),
        )
    except Exception as e:
        print(f"No se pudo conectar con MySQL: {e}")
        print("Revisa .env y que el servidor esté corriendo. Diagnóstico: bash scripts/doctor.sh")
        sys.exit(1)


def filas(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def revisar(cur, di):
    di("=" * 68)
    di("REVISIÓN DE LA BASE — rastro de la suite de pruebas")
    di("Sin --limpiar este script no ejecuta ni un solo UPDATE, INSERT o DELETE.")
    di("=" * 68)

    # 1. usuarios que no son ni del equipo ni de la demo
    intrusos = filas(cur,
        "SELECT id_usuario, nombres, email, estado, id_rol, id_area "
        "FROM usuario WHERE email LIKE %s ORDER BY id_usuario", (CORREO_DE_PRUEBAS,))
    di()
    di(f"[1] Usuarios con correo @nahan.test: {len(intrusos)}")
    for u in intrusos:
        di(f"      id={u[0]}  {u[1]!r}  {u[2]}  estado={u[3]}  rol={u[4]}  area={u[5]}")
    if not intrusos:
        di("      ninguno — la prueba que insertaba usuarios no llegó a escribir")

    # 2. estado del cliente 10, que es el que tocan las pruebas
    cliente = filas(cur,
        "SELECT id_cliente, rut, razon_social, estado FROM cliente WHERE id_cliente = 10")
    di()
    di("[2] Cliente 10 (el que usan las pruebas):")
    if cliente:
        c = cliente[0]
        di(f"      id={c[0]}  rut={c[1]}  {c[2]!r}  estado={c[3]}")
        if c[3] != "ACTIVO":
            di("      OJO: está inactivo. Puede ser obra de la prueba o algo tuyo de antes.")
    else:
        di("      no existe — la prueba no cambió nada real")

    # 3. clientes inactivos en general, para tener el panorama
    inactivos = filas(cur,
        "SELECT id_cliente, rut, razon_social FROM cliente WHERE estado <> 'ACTIVO' "
        "ORDER BY id_cliente")
    di()
    di(f"[3] Clientes no activos: {len(inactivos)}")
    for c in inactivos:
        di(f"      id={c[0]}  rut={c[1]}  {c[2]!r}")

    # 4. últimas auditorías: si hay una de deshabilitación reciente, aquí sale
    aud = filas(cur,
        "SELECT id_auditoria, id_usuario, accion, tabla_afectada, fecha, "
        "       COALESCE(datos_anteriores, ''), COALESCE(datos_nuevos, '') "
        "FROM auditoria ORDER BY id_auditoria DESC LIMIT 10")
    di()
    di(f"[4] Últimas {len(aud)} filas de auditoría (más nueva primero):")
    for a in aud:
        di(f"      #{a[0]}  usuario={a[1]}  {a[2]}  tabla={a[3]}  {a[4]}")
        if a[5]:
            di(f"           antes:   {str(a[5])[:100]}")
        if a[6]:
            di(f"           después: {str(a[6])[:100]}")

    # 5. panorama general
    di()
    di("[5] Filas por tabla:")
    tablas = [t[0] for t in filas(cur,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = DATABASE() ORDER BY table_name")]
    for t in tablas:
        n = filas(cur, f"SELECT COUNT(*) FROM `{t}`")[0][0]
        di(f"      {t:24} {n}")

    return intrusos


def limpiar(cn, cur, intrusos, di):
    if not intrusos:
        di()
        di("Nada que limpiar.")
        return

    ids = [u[0] for u in intrusos]
    marcas = ", ".join(["%s"] * len(ids))
    di()
    di(f"Borrando {len(ids)} usuario(s) de prueba y lo que cuelga de ellos...")

    # Las tablas hijas no se listan a mano: se preguntan al catálogo. Escribir
    # la lista a mano envejece mal, y una tabla olvidada haría fallar el DELETE
    # del padre con un error de clave foránea.
    hijas = filas(cur,
        "SELECT table_name, column_name FROM information_schema.key_column_usage "
        "WHERE table_schema = DATABASE() AND referenced_table_name = 'usuario' "
        "  AND referenced_column_name = 'id_usuario' "
        "ORDER BY table_name")
    di(f"      (tablas que referencian usuario: {len(hijas)})")

    for tabla, columna in hijas:
        try:
            cur.execute(f"DELETE FROM `{tabla}` WHERE `{columna}` IN ({marcas})", tuple(ids))
            if cur.rowcount:
                di(f"      {tabla}.{columna}: {cur.rowcount} fila(s)")
        except Exception as e:
            di(f"      {tabla}.{columna}: no se pudo ({e})")

    cur.execute(f"DELETE FROM usuario WHERE id_usuario IN ({marcas})", tuple(ids))
    di(f"      usuario: {cur.rowcount} fila(s)")
    cn.commit()
    di("Listo. Solo se tocaron los usuarios @nahan.test.")


def main():
    ap = argparse.ArgumentParser(description="Revisa el rastro de las pruebas en la base.")
    ap.add_argument("--limpiar", action="store_true",
                    help="borra los usuarios @nahan.test (nada más)")
    ap.add_argument("--salida", metavar="RUTA", help="guarda el informe en un archivo")
    args = ap.parse_args()

    di = Salida(args.salida)
    cn = conectar()
    cur = cn.cursor()
    try:
        intrusos = revisar(cur, di)
        if args.limpiar:
            limpiar(cn, cur, intrusos, di)
        else:
            di()
            di("(revisión de solo lectura; no se modificó nada)")
    finally:
        cur.close()
        cn.close()
        di.guardar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
