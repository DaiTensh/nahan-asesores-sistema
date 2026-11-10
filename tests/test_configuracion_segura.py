# -*- coding: utf-8 -*-
"""AUD-015 y AUD-017: la aplicación falla cerrada y no filtra el enlace de restablecimiento.

- Sin FLASK_ENV explícito se asume producción: sin SECRET_KEY propia no arranca, en lugar de
  iniciar con la clave de desarrollo (pública) que permitiría falsificar una sesión.
- El desarrollo sigue funcionando cuando se declara explícitamente.
- En producción, sin SMTP, el correo no se envía y su contenido (con el enlace) no queda en el log.
"""
import logging

import pytest

from backend import app as modulo_app
from backend.utils import correo

CLAVE_LARGA = "k" * 40
ENLACE = "http://servidor.invalid/auth/restablecer.html?token=TOKEN-DE-PRUEBA"


def _crear(monkeypatch, entorno=None, clave=None):
    for nombre, valor in (("FLASK_ENV", entorno), ("SECRET_KEY", clave)):
        if valor is None:
            monkeypatch.delenv(nombre, raising=False)
        else:
            monkeypatch.setenv(nombre, valor)
    return modulo_app.create_app()


def test_sin_entorno_ni_clave_la_aplicacion_se_niega_a_arrancar(monkeypatch):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _crear(monkeypatch)


def test_sin_entorno_y_con_la_clave_de_desarrollo_tampoco_arranca(monkeypatch):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _crear(monkeypatch, clave=modulo_app.DEFAULT_DEV_SECRET_KEY)


@pytest.mark.parametrize("entorno", ["production", "staging", "cualquier-cosa"])
def test_todo_entorno_distinto_de_desarrollo_exige_clave_propia(monkeypatch, entorno):
    with pytest.raises(RuntimeError):
        _crear(monkeypatch, entorno=entorno)


def test_sin_entorno_pero_con_clave_propia_arranca_como_produccion(monkeypatch):
    app = _crear(monkeypatch, clave=CLAVE_LARGA)

    assert app.config["DEBUG"] is False
    assert app.config["SECRET_KEY"] == CLAVE_LARGA


def test_el_desarrollo_explicito_sigue_funcionando_sin_clave(monkeypatch):
    app = _crear(monkeypatch, entorno="development")

    assert app.config["SECRET_KEY"] == modulo_app.DEFAULT_DEV_SECRET_KEY


def test_una_clave_corta_en_produccion_solo_avisa(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING):
        app = _crear(monkeypatch, entorno="production", clave="corta")

    assert app.config["SECRET_KEY"] == "corta"
    assert any("32 caracteres" in r.getMessage() for r in caplog.records)


def test_en_produccion_sin_smtp_no_se_registra_el_enlace_de_restablecimiento(monkeypatch, caplog):
    for nombre in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.delenv("FLASK_ENV", raising=False)

    with caplog.at_level(logging.DEBUG):
        enviado = correo.enviar_correo("alguien@ejemplo.invalid", "Restablecimiento", f"Use {ENLACE}")

    assert enviado is False
    texto = " ".join(r.getMessage() for r in caplog.records)
    assert "TOKEN-DE-PRUEBA" not in texto and "alguien@ejemplo.invalid" not in texto


def test_en_desarrollo_sin_smtp_el_enlace_queda_en_el_log_para_probar(monkeypatch, caplog):
    for nombre in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setenv("FLASK_ENV", "development")

    with caplog.at_level(logging.WARNING):
        correo.enviar_correo("alguien@ejemplo.invalid", "Restablecimiento", f"Use {ENLACE}")

    assert "TOKEN-DE-PRUEBA" in " ".join(r.getMessage() for r in caplog.records)


def test_produccion_con_cookie_sin_secure_deja_una_advertencia(monkeypatch, caplog):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    with caplog.at_level(logging.WARNING):
        _crear(monkeypatch, clave=CLAVE_LARGA)
    assert "SESSION_COOKIE_SECURE=false" in caplog.text


def test_produccion_con_cookie_secure_no_advierte(monkeypatch, caplog):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    with caplog.at_level(logging.WARNING):
        app = _crear(monkeypatch, clave=CLAVE_LARGA)
    try:
        assert app.config["SESSION_COOKIE_SECURE"] is True
        assert "SESSION_COOKIE_SECURE=false" not in caplog.text
    finally:
        # `create_app` configura la app global: no dejar `Secure` activo para otras pruebas.
        app.config["SESSION_COOKIE_SECURE"] = False
