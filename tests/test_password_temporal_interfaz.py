"""Interfaz y utilidades de la contraseña temporal con cambio obligatorio (sin MySQL)."""
import os
import re

import pytest

from backend.utils.security import (
    LARGO_PASSWORD_TEMPORAL, error_de_password_nueva, generar_password_temporal,
)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def leer(*ruta):
    return open(os.path.join(RAIZ, "frontend", *ruta), encoding="utf-8").read()


def test_la_temporal_generada_es_aleatoria_larga_y_cumple_la_politica():
    muestras = {generar_password_temporal() for _ in range(200)}
    assert len(muestras) == 200
    for clave in muestras:
        assert len(clave) == LARGO_PASSWORD_TEMPORAL == 14
        assert error_de_password_nueva(clave) is None
        assert not set(clave) & set("0O1lI"), "sin caracteres ambiguos"


@pytest.mark.parametrize("clave,hay_error", [("corta", True), ("a" * 8, False), ("ñ" * 37, True), (None, True), (12345678, True)])
def test_politica_de_contrasena_nueva(clave, hay_error):
    assert (error_de_password_nueva(clave) is not None) is hay_error


def test_la_pantalla_de_cambio_no_usa_almacenamiento_del_navegador_ni_guarda_secretos():
    for archivo in (("auth", "cambiar_password.js"), ("usuarios", "usuarios.js"), ("assets", "js", "permissions.js")):
        js = leer(*archivo)
        assert "localStorage" not in js and "sessionStorage.setItem(\"password" not in js, archivo
        assert "console.log" not in js, archivo


def test_el_login_y_los_permisos_dependen_del_estado_que_declara_el_servidor():
    assert "data.usuario.debe_cambiar_password" in leer("auth", "login.js")
    assert "./cambiar_password.html" in leer("auth", "login.js")
    permisos = leer("assets", "js", "permissions.js")
    assert "data.debe_cambiar_password" in permisos and 'endsWith("/auth/cambiar_password.html")' in permisos
    # La pantalla de cambio no se redirige a sí misma (sin bucles) y envía a login si no hay sesión.
    js = leer("auth", "cambiar_password.js")
    assert "response.status === 401" in js and "cambiar_password.html" not in js


def test_el_alta_ya_no_pide_contrasena_y_el_aviso_se_muestra_una_sola_vez():
    html = leer("usuarios", "usuarios.html")
    assert 'id="password"' not in html and 'id="panelPasswordTemporal"' in html and "una sola vez" in html
    js = leer("usuarios", "usuarios.js")
    assert "password:" not in js.split("const usuario = {")[1].split("};")[0], "el alta no envía contraseña"
    assert "restablecer-password" in js and "confirmarAccion(" in js and "confirmar: true" in js
    assert 'valorPasswordTemporal.value = "";' in js, "al cerrar, la temporal se borra de la pantalla"
    assert "usuarioActual.id_usuario !== usuario.id_usuario" in js, "no se ofrece restablecer la propia cuenta"


def test_la_pantalla_de_cambio_declara_politica_y_campos():
    html = leer("auth", "cambiar_password.html")
    for identificador in ("passwordActual", "passwordNueva", "confirmacion"):
        assert f'id="{identificador}"' in html
    assert 'minlength="8"' in html and "contraseña personal" in html
