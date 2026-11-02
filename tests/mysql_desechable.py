"""Servidor MySQL desechable para las pruebas de RF60.

Levanta un `mysqld` propio en un directorio temporal, con puerto efímero y sin
tocar ninguna base existente, para probar de verdad el volcado y la
restauración. Se apaga y se borra al terminar. Si en la máquina no hay
mysqld/mysqldump, las pruebas que lo necesitan se omiten.

Nunca se conecta al puerto 3306 ni usa las variables DB_* del desarrollador.
"""
import os
import shutil
import socket
import subprocess
import tempfile
import time

import mysql.connector

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESQUEMA = os.path.join(RAIZ, "database", "nahan_asesores.sql")

BASE_APP = "nahan_prueba_rf60"
USUARIO_APP = "nahan_app_prueba"
CLAVE_APP = "clave-ficticia-solo-para-pruebas"


def herramientas_disponibles():
    return bool(shutil.which("mysqld") and shutil.which("mysqldump"))


def _puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _dividir_sentencias(texto):
    """Separa por «;» respetando comillas simples y quitando comentarios de línea."""
    sin_comentarios = "\n".join(l for l in texto.splitlines() if not l.strip().startswith("--"))
    sentencias, actual, comilla = [], [], False
    for caracter in sin_comentarios:
        if caracter == "'":
            comilla = not comilla
        if caracter == ";" and not comilla:
            sentencia = "".join(actual).strip()
            if sentencia:
                sentencias.append(sentencia)
            actual = []
        else:
            actual.append(caracter)
    return sentencias


class MySQLDesechable:
    def __init__(self):
        self.carpeta = tempfile.mkdtemp(prefix="nahan-")
        self.puerto = _puerto_libre()
        assert self.puerto != 3306
        self.proceso = None

    def iniciar(self):
        datos = os.path.join(self.carpeta, "datos")
        base = [shutil.which("mysqld"), "--no-defaults", f"--datadir={datos}"]
        subprocess.run(base + ["--initialize-insecure"], check=True, capture_output=True, timeout=120)
        self.proceso = subprocess.Popen(
            base + [
                f"--port={self.puerto}", "--bind-address=127.0.0.1", "--mysqlx=OFF",
                f"--socket={os.path.join(self.carpeta, 'm.sock')}",
                f"--pid-file={os.path.join(self.carpeta, 'm.pid')}",
                f"--log-error={os.path.join(self.carpeta, 'error.log')}",
                "--skip-log-bin", "--innodb-buffer-pool-size=64M", "--max-connections=50",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        limite = time.time() + 90
        while time.time() < limite:
            try:
                self.conectar().close()
                break
            except mysql.connector.Error:
                if self.proceso.poll() is not None:
                    raise RuntimeError("mysqld terminó al iniciar; revise " + os.path.join(self.carpeta, "error.log"))
                time.sleep(0.3)
        else:
            raise RuntimeError("mysqld no respondió a tiempo")
        self._preparar_base()
        return self

    def conectar(self, usuario="root", clave="", base=None, **extra):
        return mysql.connector.connect(
            host="127.0.0.1", port=self.puerto, user=usuario, password=clave, database=base,
            connection_timeout=5, **extra)

    def _preparar_base(self):
        cn = self.conectar()
        cur = cn.cursor()
        cur.execute(f"CREATE DATABASE {BASE_APP} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        # Mismos privilegios que la cuenta de la aplicación en el servidor real:
        # sin DROP, LOCK TABLES, TRIGGER ni PROCESS.
        cur.execute(f"CREATE USER '{USUARIO_APP}'@'%' IDENTIFIED BY '{CLAVE_APP}'")
        cur.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, REFERENCES, INDEX, ALTER "
            f"ON {BASE_APP}.* TO '{USUARIO_APP}'@'%'")
        cn.close()

    def cargar_esquema(self, base=BASE_APP):
        """Crea las tablas de database/nahan_asesores.sql en `base`, sin su DROP/CREATE DATABASE."""
        with open(ESQUEMA, encoding="utf-8") as archivo:
            texto = archivo.read()
        texto = texto[texto.index("USE nahan_asesores;") + len("USE nahan_asesores;"):]
        cn = self.conectar(base=base)
        cur = cn.cursor()
        for sentencia in _dividir_sentencias(texto):
            cur.execute(sentencia)
        cn.commit()
        cn.close()

    def detener(self):
        if self.proceso and self.proceso.poll() is None:
            self.proceso.terminate()
            try:
                self.proceso.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proceso.kill()
        shutil.rmtree(self.carpeta, ignore_errors=True)


TABLAS_DE_NEGOCIO = (
    "rol", "area", "usuario", "cliente", "cliente_reciente", "cliente_area", "tarea", "documento",
    "tarea_documento", "observacion_cliente", "comentario_tarea", "revision_tarea", "notificacion",
    "tiempo_trabajado", "tarifa_hora", "registro_tiempo", "cobro", "reporte", "area_reporte",
    "auditoria", "parametros_sistema", "token_recuperacion",
)


def sembrar_datos_ficticios(cn, sufijo=""):
    """Datos inventados (nada real) con tildes, ñ y comillas para probar el escape del volcado."""
    cur = cn.cursor()
    cur.execute(
        "INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) VALUES "
        "(1, 3, %s, %s, 'hash-ficticio-1'), (2, 1, %s, %s, 'hash-ficticio-2')",
        (f"Admin Ficticia{sufijo}", f"admin{sufijo}@ejemplo.invalid", f"Usuaria Jurídica{sufijo}",
         f"juridica{sufijo}@ejemplo.invalid"))
    cur.execute("SELECT MIN(id_usuario) FROM usuario")
    admin = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO cliente (rut, razon_social, email, telefono, direccion) VALUES "
        "('11.111.111-1', %s, 'a@ejemplo.invalid', '+56 9 0000 0001', %s), "
        "('22.222.222-2', %s, 'b@ejemplo.invalid', '+56 9 0000 0002', 'Calle Falsa 123; piso 2')",
        (f"Ñandú y Compañía «Ficticia» S.A.{sufijo}", "Av. O'Higgins 1 \\ esquina \"X\"", f"Cliente Dos{sufijo}"))
    cur.execute(
        "INSERT INTO observacion_cliente (id_cliente, id_usuario, texto) "
        "SELECT MIN(id_cliente), %s, %s FROM cliente",
        (admin, "Línea uno\nLínea dos con 'comillas', \"dobles\", tab\t y ; punto y coma -- y /* comentario */"))
    cur.execute(
        "INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, descripcion, fecha_vencimiento) "
        "SELECT MIN(id_cliente), 1, %s, %s, %s, %s, '2026-12-31' FROM cliente",
        (admin, admin, "Declaración «Renta» 2026", "Texto con símbolo ✓, barra \\ invertida y \x00 no"))
    cur.execute(
        "INSERT INTO documento (id_cliente, nombre_documento, url_archivo, subido_por) "
        "SELECT MIN(id_cliente), 'Contrato.pdf', 'aaaaaaaabbbbbbbbccccccccdddddddd.pdf', %s FROM cliente",
        (admin,))
    cn.commit()
    cur.close()


def contenido_de_tablas(cn, tablas=TABLAS_DE_NEGOCIO):
    """{tabla: filas ordenadas} para comparar el estado completo antes y después de restaurar."""
    cur = cn.cursor()
    resultado = {}
    for tabla in tablas:
        cur.execute(f"SELECT * FROM `{tabla}` ORDER BY 1")
        resultado[tabla] = [tuple(fila) for fila in cur.fetchall()]
    cur.close()
    return resultado
