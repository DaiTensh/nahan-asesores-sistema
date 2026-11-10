# -*- coding: utf-8 -*-
"""RF26 y RF53 contra dependencias locales reales (sin servicios externos).

* RF26: `enviar_correo` habla SMTP de verdad (EHLO, STARTTLS con verificación de certificado, AUTH
  PLAIN y DATA) contra un servidor SMTP local de prueba que escucha solo en 127.0.0.1. Comprueba que
  el correo de restablecimiento llega con el enlace. NO prueba un proveedor real (Gmail, SES, etc.).
* RF53: `python -m backend.tareas_programadas` se ejecuta como proceso independiente (como lo hace
  systemd) contra el MySQL desechable y crea los avisos esperados, sin duplicarlos. NO prueba que
  `nahan-vencimientos.timer` dispare a las 07:00 en un servidor: eso solo se observa en el servidor.
"""
import base64
import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading

import pytest

from backend.utils import correo
from tests.mysql_desechable import (
    BASE_APP, CLAVE_APP, RAIZ, USUARIO_APP, MySQLDesechable, herramientas_disponibles, sembrar_datos_ficticios,
)

CLAVE_SMTP = "clave-smtp-ficticia"


class SMTPLocal:
    """Servidor SMTP mínimo con STARTTLS y AUTH PLAIN; guarda los mensajes recibidos."""

    def __init__(self, certificado, clave):
        self.contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.contexto.load_cert_chain(certificado, clave)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.puerto = self.sock.getsockname()[1]
        self.mensajes, self.credenciales = [], []
        threading.Thread(target=self._aceptar, daemon=True).start()

    def _aceptar(self):
        while True:
            try:
                conexion, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._atender, args=(conexion,), daemon=True).start()

    def _atender(self, conexion):
        try:
            f = conexion.makefile("rwb", buffering=0)
            f.write(b"220 local ESMTP\r\n")
            while True:
                linea = f.readline().decode("utf-8", "replace").strip()
                orden = linea.upper()
                if orden.startswith("EHLO"):
                    f.write(b"250-local\r\n250-STARTTLS\r\n250-AUTH PLAIN\r\n250 8BITMIME\r\n")
                elif orden == "STARTTLS":
                    f.write(b"220 listo\r\n")
                    conexion = self.contexto.wrap_socket(conexion, server_side=True)
                    f = conexion.makefile("rwb", buffering=0)
                elif orden.startswith("AUTH PLAIN"):
                    partes = base64.b64decode(linea.split()[2]).split(b"\0")
                    self.credenciales.append((partes[1].decode(), partes[2].decode()))
                    f.write(b"235 ok\r\n")
                elif orden.startswith(("MAIL", "RCPT")):
                    f.write(b"250 ok\r\n")
                elif orden == "DATA":
                    f.write(b"354 fin con .\r\n")
                    cuerpo = []
                    while True:
                        l = f.readline()
                        if l.strip() == b".":
                            break
                        cuerpo.append(l)
                    self.mensajes.append(b"".join(cuerpo).decode("utf-8", "replace"))
                    f.write(b"250 recibido\r\n")
                elif orden == "QUIT":
                    f.write(b"221 adios\r\n")
                    return
                else:
                    f.write(b"250 ok\r\n")
        except Exception:
            pass
        finally:
            conexion.close()

    def cerrar(self):
        self.sock.close()


@pytest.fixture
def smtp_local(tmp_path, monkeypatch):
    if not shutil.which("openssl"):
        pytest.skip("openssl no disponible")
    crt, key = str(tmp_path / "c.pem"), str(tmp_path / "k.pem")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", crt,
                    "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1"],
                   check=True, capture_output=True)
    servidor = SMTPLocal(crt, key)
    # Se confía solo en el certificado de prueba; la verificación de certificado sigue activa.
    original = ssl.create_default_context
    monkeypatch.setattr(correo.ssl, "create_default_context", lambda *a, **k: original(cafile=crt))
    for k, v in {"SMTP_HOST": "127.0.0.1", "SMTP_PORT": str(servidor.puerto), "SMTP_USER": "sistema@ejemplo.invalid",
                 "SMTP_PASSWORD": CLAVE_SMTP, "SMTP_FROM": "sistema@ejemplo.invalid"}.items():
        monkeypatch.setenv(k, v)
    yield servidor
    servidor.cerrar()


def test_rf26_el_correo_de_restablecimiento_sale_por_smtp_con_starttls(smtp_local):
    enlace = "https://nahan.ejemplo.invalid/auth/restablecer.html?token=TOKEN-FICTICIO"
    cuerpo = correo.cuerpo_restablecimiento("Ana", enlace, 30)
    assert correo.enviar_correo("ana@ejemplo.invalid", "Restablecer contraseña", cuerpo) is True
    assert smtp_local.credenciales == [("sistema@ejemplo.invalid", CLAVE_SMTP)]
    assert len(smtp_local.mensajes) == 1
    recibido = smtp_local.mensajes[0]
    assert "To: ana@ejemplo.invalid" in recibido and "Subject:" in recibido
    # El cuerpo viaja codificado (utf-8); se decodifica para comprobar el enlace.
    import email
    texto = email.message_from_string(recibido).get_payload(decode=True).decode("utf-8")
    assert enlace in texto and "30 minutos" in texto


def test_rf26_un_certificado_no_confiable_hace_fallar_el_envio_sin_lanzar_excepcion(smtp_local, monkeypatch):
    monkeypatch.undo()  # vuelve al contexto por defecto: el certificado autofirmado no es de confianza
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", str(smtp_local.puerto))
    monkeypatch.setenv("SMTP_USER", "u@ejemplo.invalid")
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    assert correo.enviar_correo("a@ejemplo.invalid", "Asunto", "Cuerpo") is False
    assert smtp_local.mensajes == []


# ------------------------------------------------------------------- RF53
@pytest.mark.skipif(not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
                    reason="requiere mysqld")
def test_rf53_el_proceso_programado_funciona_como_proceso_independiente_y_no_duplica():
    servidor = MySQLDesechable().iniciar()
    try:
        root = servidor.conectar()
        c = root.cursor()
        c.execute(f"DROP DATABASE IF EXISTS {BASE_APP}")
        c.execute(f"CREATE DATABASE {BASE_APP} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        root.close()
        servidor.cargar_esquema()
        cn = servidor.conectar(base=BASE_APP)
        sembrar_datos_ficticios(cn)
        cur = cn.cursor()
        # La tarea sembrada vence en 2026-12-31: se ubica en 2 días (dentro de la ventana) y otra en 30 (fuera).
        cur.execute("UPDATE tarea SET fecha_vencimiento = CURDATE() + INTERVAL 2 DAY WHERE id_tarea = 1")
        cur.execute("INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, fecha_vencimiento) "
                    "VALUES (1, 1, 1, 1, 'Lejana', CURDATE() + INTERVAL 30 DAY)")
        cn.commit()
        cn.close()
        entorno = {**os.environ, "DB_HOST": "127.0.0.1", "DB_PORT": str(servidor.puerto), "DB_USER": USUARIO_APP,
                   "DB_PASSWORD": CLAVE_APP, "DB_NAME": BASE_APP, "FLASK_ENV": "development",
                   "DIAS_ANTICIPACION_VENCIMIENTO": "3"}

        def correr():
            return subprocess.run([sys.executable, "-m", "backend.tareas_programadas"], cwd=RAIZ, env={**entorno, "PYTHONPATH": RAIZ},
                                  capture_output=True, text=True, timeout=60)

        def avisos():
            cn2 = servidor.conectar(base=BASE_APP)
            cu = cn2.cursor()
            cu.execute("SELECT id_usuario, tipo, mensaje FROM notificacion WHERE tipo = 'VENCIMIENTO_PROXIMO'")
            filas = cu.fetchall()
            cn2.close()
            return filas

        primera = correr()
        assert primera.returncode == 0, primera.stderr
        filas = avisos()
        assert len(filas) == 1 and filas[0][0] == 1 and "Declaración" in filas[0][2]  # solo la tarea por vencer
        assert correr().returncode == 0
        assert len(avisos()) == 1  # segunda pasada el mismo día: sin duplicados
    finally:
        servidor.detener()
