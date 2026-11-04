# -*- coding: utf-8 -*-
"""AUD-016: una base de datos que no responde no debe colgar la solicitud indefinidamente, y una solicitud
lenta no debe ocupar un worker entero de Gunicorn."""
import os
import re

from backend.config import db

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _capturar(monkeypatch):
    capturado = {}
    monkeypatch.setattr(db.mysql.connector, "connect", lambda **kw: capturado.update(kw) or object())
    return capturado


def test_la_conexion_a_mysql_lleva_un_timeout_por_defecto(monkeypatch):
    monkeypatch.delenv("DB_CONNECT_TIMEOUT", raising=False)
    capturado = _capturar(monkeypatch)

    db.get_connection()

    assert capturado["connection_timeout"] == 10


def test_el_timeout_de_conexion_se_configura_y_un_valor_invalido_no_rompe_el_arranque(monkeypatch):
    capturado = _capturar(monkeypatch)
    for valor, esperado in (("3", 3), ("0", 1), ("abc", 10), ("", 10)):
        monkeypatch.setenv("DB_CONNECT_TIMEOUT", valor)
        db.get_connection()
        assert capturado["connection_timeout"] == esperado, valor


def test_gunicorn_usa_hilos_para_que_una_solicitud_lenta_no_bloquee_un_worker():
    with open(os.path.join(RAIZ, "deploy", "systemd", "nahan.service"), encoding="utf-8") as archivo:
        unidad = archivo.read()
    exec_start = next(l for l in unidad.splitlines() if l.startswith("ExecStart="))

    assert "--worker-class gthread" in exec_start
    assert int(re.search(r"--threads (\d+)", exec_start).group(1)) >= 2
    assert re.search(r"--timeout 300", exec_start), "el respaldo manual (RF60) sigue necesitando hasta 300 s"
