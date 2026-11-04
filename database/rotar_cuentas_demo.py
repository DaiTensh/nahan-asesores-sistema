#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cierra el riesgo de las cuentas de demostración que sembró database/seed_dev.py.

Esas siete cuentas (@nahan.local) comparten una contraseña de desarrollo que está
escrita en un repositorio público. Si existen en un servidor, hay que rotarlas o
desactivarlas antes de exponerlo. Este script lo hace sin tocar nada más.

    python database/rotar_cuentas_demo.py                       # SOLO INFORMA; no cambia nada
    python database/rotar_cuentas_demo.py --aplicar             # nueva contraseña aleatoria por cuenta
    python database/rotar_cuentas_demo.py --aplicar --desactivar  # las deja INACTIVAS (no pueden entrar)

Qué hace y qué no:
  - Solo toca los siete correos de la siembra. Ninguna otra cuenta.
  - Sin --aplicar informa cuáles aceptan todavía la contraseña pública (lectura, sin cambios).
  - Con --aplicar solo cambia las cuentas que la aceptan; cada una recibe una contraseña
    aleatoria que se IMPRIME UNA SOLA VEZ en pantalla (no se guarda en ningún archivo).
    Ejecútelo en una sesión interactiva y entregue cada contraseña por un canal privado.
  - Con --desactivar no genera contraseñas: pone la cuenta en INACTIVO.
  - Usa la conexión de .env (DB_*). En el servidor, hacer antes una copia de la base.
"""
import argparse
import os
import secrets
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "database"))

from backend.config.db import get_connection  # noqa: E402
from backend.utils.security import check_password, hash_password  # noqa: E402
import seed_dev  # noqa: E402

CORREOS = [email for _nombres, email, _rol, _area in seed_dev.USUARIOS]


def _contrasena_nueva():
    # 18 caracteres sin signos ambiguos: se entrega a una persona, no a una máquina.
    alfabeto = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(18))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rota o desactiva las cuentas de demostración de seed_dev.py")
    ap.add_argument("--aplicar", action="store_true", help="realiza el cambio (sin esto solo informa)")
    ap.add_argument("--desactivar", action="store_true", help="con --aplicar: desactiva en lugar de rotar")
    args = ap.parse_args(argv)
    if args.desactivar and not args.aplicar:
        print("--desactivar solo tiene efecto junto con --aplicar.")
        return 2

    conexion = get_connection()
    if conexion is None:
        print("No hay conexión con MySQL. Revise .env (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME).")
        return 1
    cursor = conexion.cursor(dictionary=True)
    marcadores = ", ".join(["%s"] * len(CORREOS))
    cursor.execute(
        f"SELECT id_usuario, email, estado, password_hash FROM usuario WHERE email IN ({marcadores}) ORDER BY id_usuario",
        tuple(CORREOS),
    )
    cuentas = cursor.fetchall()
    if not cuentas:
        print("No existe ninguna cuenta de demostración en esta base. Nada que hacer.")
        conexion.close()
        return 0

    print(f"{'ID':>4}  {'ESTADO':<9} {'CONTRASEÑA PÚBLICA VIGENTE':<27} CORREO")
    expuestas = []
    for cuenta in cuentas:
        publica = bool(cuenta["password_hash"]) and check_password(seed_dev.PASSWORD_PUBLICA_DE_DESARROLLO, cuenta["password_hash"])
        if publica:
            expuestas.append(cuenta)
        print(f"{cuenta['id_usuario']:>4}  {cuenta['estado']:<9} {'SÍ' if publica else 'no':<27} {cuenta['email']}")

    activas_expuestas = [c for c in expuestas if c["estado"] == "ACTIVO"]
    print(f"\n{len(expuestas)} cuenta(s) aceptan la contraseña pública; {len(activas_expuestas)} de ellas están activas.")

    if not args.aplicar:
        print("Modo informe: no se cambió nada. Para corregirlo, repita con --aplicar.")
        conexion.close()
        return 1 if activas_expuestas else 0

    try:
        if args.desactivar:
            for cuenta in expuestas:
                cursor.execute("UPDATE usuario SET estado = 'INACTIVO' WHERE id_usuario = %s", (cuenta["id_usuario"],))
            conexion.commit()
            print(f"Desactivadas: {len(expuestas)}.")
        else:
            print("\nContraseñas nuevas (se muestran una sola vez; entréguelas por un canal privado):")
            for cuenta in expuestas:
                nueva = _contrasena_nueva()
                cursor.execute(
                    "UPDATE usuario SET password_hash = %s WHERE id_usuario = %s",
                    (hash_password(nueva), cuenta["id_usuario"]),
                )
                print(f"  {cuenta['email']:<36} {nueva}")
            conexion.commit()
            print(f"\nRotadas: {len(expuestas)}.")
    except Exception:
        conexion.rollback()
        raise
    finally:
        cursor.close()
        conexion.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
