#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Revisa, sin modificar nada, los RUT de los clientes de una base existente.

La aplicación exige RUT con dígito verificador válido (módulo 11) y evita que el
mismo RUT se registre con distinto formato. Una base creada antes de esa regla
puede contener RUT que no la cumplen. Este script los lista para que alguien con
autoridad sobre los datos decida qué hacer:

    .venv/bin/python database/revisar_ruts.py

Sale con código 0 si todo está en orden y con 1 si hay algo que revisar. No
escribe en la base: corregir un RUT real requiere confirmar el valor correcto con
el cliente y se hace por separado, con respaldo previo. Los clientes de
demostración se corrigen solos con `python database/seed_dev.py`.
"""
import os
import sys
from collections import defaultdict

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from backend.config.db import get_connection  # noqa: E402
from backend.utils.validaciones_cliente import rut_comparable, validar_rut  # noqa: E402


def revisar(filas):
    """[(id_cliente, rut, razon_social)] -> lista de (id_cliente, rut, motivo). Función pura."""
    hallazgos = []
    por_comparable = defaultdict(list)
    for id_cliente, rut, razon in filas:
        canonico, error = validar_rut(rut)
        if error:
            hallazgos.append((id_cliente, rut, error))
            continue
        por_comparable[rut_comparable(canonico)].append((id_cliente, rut))
        if canonico != rut:
            hallazgos.append((id_cliente, rut, f"formato distinto del normalizado ({canonico})"))
    for grupo in por_comparable.values():
        if len(grupo) > 1:
            ids = ", ".join(str(i) for i, _ in grupo)
            for id_cliente, rut in grupo:
                hallazgos.append((id_cliente, rut, f"el mismo RUT figura en varios clientes ({ids})"))
    return sorted(hallazgos)


def main():
    conexion = get_connection()
    if conexion is None:
        print("No se pudo conectar con la base de datos (revise .env).")
        return 2
    try:
        cursor = conexion.cursor()
        cursor.execute("SELECT id_cliente, rut, razon_social FROM cliente ORDER BY id_cliente")
        filas = cursor.fetchall()
    finally:
        conexion.close()

    hallazgos = revisar(filas)
    nombres = {id_cliente: razon for id_cliente, _, razon in filas}
    print(f"{len(filas)} cliente(s) revisado(s).")
    for id_cliente, rut, motivo in hallazgos:
        print(f"  #{id_cliente} {rut!r} ({nombres[id_cliente]}): {motivo}")
    if not hallazgos:
        print("Todos los RUT son válidos y están normalizados.")
        return 0
    print(f"{len(hallazgos)} hallazgo(s). No se modificó nada.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
