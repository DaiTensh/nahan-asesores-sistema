"""RF60 — Respaldando históricamente la información.

Servicio de respaldo y restauración. Lo usan la API de administración
(backend/routes/respaldos_routes.py) y el proceso programado
(backend/respaldos_programados.py, ver deploy/systemd/nahan-respaldo.*).

Un respaldo es un único paquete .zip que contiene:

    manifest.json        formato, versión del esquema y huella SHA-256 de cada pieza
    base_de_datos.sql    volcado de mysqldump (sin la tabla `respaldo`)
    adjuntos/...         archivos de ADJUNTOS_DIR (RF54)

Decisiones de seguridad que conviene conocer antes de tocar este archivo:

- Las herramientas externas se llaman siempre con una lista de argumentos
  (nunca con shell) y las credenciales viajan en un archivo de opciones 0600
  que se borra al terminar: no aparecen en `ps` ni en el historial.
- La restauración no ejecuta el cliente `mysql`: reproduce el volcado con
  mysql-connector, sentencia por sentencia, después de comprobar que solo
  contiene DROP/CREATE TABLE e INSERT. Así un paquete manipulado no puede
  colar comandos del cliente (`\\!`, `source`) ni DDL ajeno a las tablas.
- Ninguna ruta llega desde el cliente: el paquete se resuelve por el nombre
  que guardó el propio sistema en la tabla `respaldo` y se valida contra su
  huella SHA-256 antes de abrirlo.
- Un solo respaldo o restauración a la vez, entre todos los procesos del
  servidor (Gunicorn y el temporizador), con un bloqueo de archivo.
"""
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import time
import zipfile
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib import util as importlib_util

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

from backend.config.db import get_connection

logger = logging.getLogger(__name__)

RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FORMATO_RESPALDO = 1
APLICACION = "nahan-asesores"
TABLA_HISTORIAL = "respaldo"
# Estado operativo, no información de negocio: no viaja en el paquete y una
# restauración no lo toca (el historial de respaldos debe sobrevivirla, y los
# intentos de login fallidos de SEC-02 no deben «perdonarse» al restaurar).
TABLAS_EXCLUIDAS = (TABLA_HISTORIAL, "intento_login_fallido")

MIEMBRO_MANIFIESTO = "manifest.json"
MIEMBRO_SQL = "base_de_datos.sql"
PREFIJO_ADJUNTOS = "adjuntos/"

ARCHIVO_BLOQUEO = ".operacion.lock"
ARCHIVO_MANTENIMIENTO = ".restauracion_en_curso"
PREFIJO_TRABAJO = ".trabajo-"
PREFIJO_PARCIAL = ".parcial-"

OPERACION_RESPALDO = "RESPALDO"
OPERACION_RESTAURACION = "RESTAURACION"
TIPO_MANUAL = "MANUAL"
TIPO_PROGRAMADO = "PROGRAMADO"
TIPO_PREVIO = "PREVIO_RESTAURACION"
TIPOS_RESPALDO = (TIPO_MANUAL, TIPO_PROGRAMADO, TIPO_PREVIO)
ESTADO_EN_CURSO = "EN_CURSO"
ESTADO_EXITOSO = "EXITOSO"
ESTADO_FALLIDO = "FALLIDO"

CONFIRMACION_RESTAURAR = "RESTAURAR"

RETENCION_DEFECTO = 30
RETENCION_MINIMA = 3
TIMEOUT_DEFECTO = 600
LIMITE_MB_DEFECTO = 4096
MAXIMO_MIEMBROS = 100000
ESPACIO_MINIMO_BYTES = 64 * 1024 * 1024
BLOQUE = 1024 * 1024

PATRON_NOMBRE_PAQUETE = re.compile(r"^nahan-respaldo-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}\.zip\Z")
PATRON_IDENTIFICADOR = re.compile(r"^[A-Za-z0-9_]{1,64}\Z")
PATRON_HOST = re.compile(r"^[A-Za-z0-9._:\-]{1,255}\Z")
PATRON_COMPONENTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")
PATRON_SHA256 = re.compile(r"^[0-9a-f]{64}\Z")

_MENSAJE_RESPALDO_INVALIDO = "El respaldo no es válido"


class ErrorRespaldo(Exception):
    """Error con un mensaje apto para mostrarse al administrador."""

    estado_http = 500
    codigo = "ERROR_RESPALDO"

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


class OperacionEnCurso(ErrorRespaldo):
    estado_http = 409
    codigo = "OPERACION_EN_CURSO"


class AlmacenamientoNoValido(ErrorRespaldo):
    estado_http = 503
    codigo = "ALMACENAMIENTO_NO_VALIDO"


class RespaldoNoValido(ErrorRespaldo):
    estado_http = 422
    codigo = "RESPALDO_NO_VALIDO"


class RespaldoNoEncontrado(ErrorRespaldo):
    estado_http = 404
    codigo = "RESPALDO_NO_ENCONTRADO"


class OperacionNoPermitida(ErrorRespaldo):
    estado_http = 403
    codigo = "OPERACION_NO_PERMITIDA"


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

def _bool(valor, defecto=False):
    if valor is None:
        return defecto
    return str(valor).strip().lower() in {"1", "true", "yes", "on"}


def _entero(valor, defecto, minimo, maximo):
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        return defecto
    return min(max(numero, minimo), maximo)


class ConfigRespaldo:
    """Configuración leída del entorno en el momento de usarla.

    Las credenciales de MySQL salen de las mismas DB_* de la aplicación, salvo
    que se definan RESPALDO_DB_USER/RESPALDO_DB_PASSWORD (respaldo) o
    RESTAURACION_DB_USER/RESTAURACION_DB_PASSWORD (restauración): así un
    despliegue puede darle a la restauración una cuenta con privilegios que la
    aplicación web no necesita tener.
    """

    def __init__(self, entorno=None):
        env = os.environ if entorno is None else entorno

        self.directorio = (env.get("RESPALDO_DIR") or "").strip()
        self.directorio_adjuntos = (
            (env.get("ADJUNTOS_DIR") or "").strip()
            or os.path.join(os.getcwd(), "uploads", "tareas")
        )
        self.retencion_maxima = _entero(
            env.get("RESPALDO_RETENCION_MAXIMA"), RETENCION_DEFECTO, RETENCION_MINIMA, 3650
        )
        self.timeout = _entero(env.get("RESPALDO_TIMEOUT_SEGUNDOS"), TIMEOUT_DEFECTO, 5, 7200)
        self.limite_bytes = _entero(env.get("RESPALDO_MAX_MB"), LIMITE_MB_DEFECTO, 1, 1048576) * 1024 * 1024
        self.exigir_dispositivo_separado = _bool(env.get("RESPALDO_EXIGIR_DISPOSITIVO_SEPARADO"))
        self.mysqldump = (env.get("MYSQLDUMP_BIN") or "mysqldump").strip()

        self.db_host = (env.get("DB_HOST") or "127.0.0.1").strip()
        self.db_port = _entero(env.get("DB_PORT"), 3306, 1, 65535)
        self.db_nombre = (env.get("DB_NAME") or "").strip()

        if (env.get("RESPALDO_DB_USER") or "").strip():
            self._respaldo_usuario = env.get("RESPALDO_DB_USER").strip()
            self._respaldo_clave = env.get("RESPALDO_DB_PASSWORD") or ""
        else:
            self._respaldo_usuario = (env.get("DB_USER") or "").strip()
            self._respaldo_clave = env.get("DB_PASSWORD") or ""

        self.restauracion_habilitada = _bool(env.get("RESTAURACION_HABILITADA"))
        self.restauracion_db_nombre = (env.get("RESTAURACION_DB_NAME") or "").strip() or self.db_nombre
        if (env.get("RESTAURACION_DB_USER") or "").strip():
            self._restauracion_usuario = env.get("RESTAURACION_DB_USER").strip()
            self._restauracion_clave = env.get("RESTAURACION_DB_PASSWORD") or ""
        else:
            self._restauracion_usuario = self._respaldo_usuario
            self._restauracion_clave = self._respaldo_clave

    def __repr__(self):
        return f"<ConfigRespaldo directorio={self.directorio!r} base={self.db_nombre!r}>"

    @property
    def credenciales_respaldo(self):
        return self._respaldo_usuario, self._respaldo_clave

    @property
    def credenciales_restauracion(self):
        return self._restauracion_usuario, self._restauracion_clave

    @property
    def restaura_base_activa(self):
        return self.restauracion_db_nombre == self.db_nombre


def _validar_conexion(host, puerto, usuario, clave, base):
    """Rechaza valores que no puedan ir en un archivo de opciones ni como nombre de base."""
    if not PATRON_HOST.match(host or "") or host.startswith("-"):
        raise ErrorRespaldo("DB_HOST no es válido.")
    if not 1 <= puerto <= 65535:
        raise ErrorRespaldo("DB_PORT no es válido.")
    if not usuario or any(ord(c) < 32 for c in usuario) or len(usuario) > 80:
        raise ErrorRespaldo("El usuario de MySQL para respaldos no es válido.")
    if any(ord(c) < 32 for c in clave):
        raise ErrorRespaldo("La contraseña de MySQL para respaldos contiene caracteres no admitidos.")
    if not PATRON_IDENTIFICADOR.match(base or ""):
        raise ErrorRespaldo("El nombre de la base de datos no es válido.")


# ---------------------------------------------------------------------------
# Almacenamiento
# ---------------------------------------------------------------------------

def _real(ruta):
    return os.path.realpath(os.path.abspath(ruta))


def _dentro_de(ruta, base):
    ruta, base = _real(ruta), _real(base)
    try:
        return os.path.commonpath([ruta, base]) == base
    except ValueError:  # unidades distintas en Windows
        return False


def _verificacion(clave, nivel, mensaje):
    return {"clave": clave, "nivel": nivel, "mensaje": mensaje}


def _dispositivo_distinto(ruta):
    """True si `ruta` está en otro dispositivo que la aplicación; None si no se pudo comprobar."""
    try:
        return os.stat(ruta).st_dev != os.stat(RAIZ_PROYECTO).st_dev
    except OSError:
        return None


def evaluar_almacenamiento(config, crear=False, tamano_referencia=0):
    """Comprueba que RESPALDO_DIR sirva como destino seguro y separado (CA5).

    Con `crear=True` crea la carpeta (solo el último nivel: si falta el
    superior, lo normal es un volumen sin montar y no hay que escribir en el
    disco raíz) y le deja permisos 0700.

    Devuelve {"directorio", "apto", "independiente", "verificaciones"}; cada
    verificación lleva nivel `ok`, `aviso` o `error`. `independiente` solo
    afirma lo que se puede comprobar desde el sistema operativo: que la
    carpeta esté en un dispositivo distinto del de la aplicación. Que ese
    dispositivo sea además otro disco físico, otra máquina u otra zona de
    disponibilidad no se puede demostrar desde aquí.
    """
    verificaciones = []
    resultado = {"directorio": config.directorio, "apto": False, "independiente": None,
                 "verificaciones": verificaciones}

    if not config.directorio:
        verificaciones.append(_verificacion(
            "configurado", "error", "RESPALDO_DIR no está configurado: no hay dónde guardar los respaldos."))
        return resultado
    if not os.path.isabs(config.directorio):
        verificaciones.append(_verificacion("absoluta", "error", "RESPALDO_DIR debe ser una ruta absoluta."))
        return resultado

    ruta = _real(config.directorio)
    verificaciones.append(_verificacion("configurado", "ok", "RESPALDO_DIR está configurado."))

    if ruta == os.path.dirname(ruta):
        verificaciones.append(_verificacion("ubicacion", "error", "RESPALDO_DIR no puede ser la raíz del sistema."))
        return resultado
    if _dentro_de(ruta, RAIZ_PROYECTO) or _dentro_de(ruta, config.directorio_adjuntos) \
            or _dentro_de(config.directorio_adjuntos, ruta):
        verificaciones.append(_verificacion(
            "ubicacion", "error",
            "RESPALDO_DIR no puede estar dentro del proyecto ni del directorio de adjuntos "
            "(ni contenerlo): quedaría expuesto o se respaldaría a sí mismo."))
        return resultado
    verificaciones.append(_verificacion("ubicacion", "ok", "Fuera del proyecto y de los adjuntos."))

    if not os.path.isdir(ruta):
        if not crear:
            superior = os.path.dirname(ruta)
            if os.path.isdir(superior) and os.access(superior, os.W_OK):
                verificaciones.append(_verificacion(
                    "existe", "aviso", "La carpeta todavía no existe; se creará con el primer respaldo."))
                resultado["apto"] = True
            else:
                verificaciones.append(_verificacion(
                    "existe", "error",
                    "La carpeta no existe y no se puede crear (falta el directorio superior o no tiene permiso de escritura). "
                    "Si es un volumen externo, compruebe que esté montado."))
            return resultado
        try:
            os.mkdir(ruta, 0o700)
        except OSError as error:
            verificaciones.append(_verificacion(
                "existe", "error",
                f"No se pudo crear la carpeta de respaldos ({error.strerror or 'error'}). "
                "Si es un volumen externo, compruebe que esté montado."))
            return resultado
    verificaciones.append(_verificacion("existe", "ok", "La carpeta existe."))

    if os.name == "posix":
        estado = os.stat(ruta)
        if estado.st_uid != os.geteuid():
            verificaciones.append(_verificacion(
                "permisos", "error", "La carpeta de respaldos no pertenece al usuario que ejecuta la aplicación."))
            return resultado
        if estado.st_mode & 0o077:
            try:
                os.chmod(ruta, 0o700)
            except OSError:
                pass
        if os.stat(ruta).st_mode & 0o077:
            verificaciones.append(_verificacion(
                "permisos", "error", "La carpeta de respaldos es accesible para otros usuarios (debe ser 0700)."))
            return resultado
        verificaciones.append(_verificacion("permisos", "ok", "Solo el propietario puede leer la carpeta (0700)."))
    else:
        verificaciones.append(_verificacion(
            "permisos", "aviso", "Los permisos de archivo no se pueden comprobar en este sistema operativo."))

    try:
        prueba = os.path.join(ruta, f"{PREFIJO_PARCIAL}{secrets.token_hex(4)}.prueba")
        with open(prueba, "wb") as archivo:
            archivo.write(b"ok")
        os.remove(prueba)
        verificaciones.append(_verificacion("escritura", "ok", "Se puede escribir en la carpeta."))
    except OSError:
        verificaciones.append(_verificacion("escritura", "error", "No se puede escribir en la carpeta de respaldos."))
        return resultado

    libre = shutil.disk_usage(ruta).free
    necesario = max(ESPACIO_MINIMO_BYTES, int(tamano_referencia * 3))
    if libre < necesario:
        verificaciones.append(_verificacion(
            "espacio", "error", f"Espacio libre insuficiente ({libre // (1024 * 1024)} MB)."))
    else:
        verificaciones.append(_verificacion("espacio", "ok", f"Espacio libre: {libre // (1024 * 1024)} MB."))

    separado = _dispositivo_distinto(ruta)
    resultado["independiente"] = separado
    if separado:
        verificaciones.append(_verificacion(
            "independencia", "ok", "La carpeta está en un dispositivo distinto del de la aplicación."))
    elif config.exigir_dispositivo_separado:
        verificaciones.append(_verificacion(
            "independencia", "error",
            "La carpeta está en el mismo dispositivo que la aplicación y RESPALDO_EXIGIR_DISPOSITIVO_SEPARADO "
            "está activo."))
    else:
        verificaciones.append(_verificacion(
            "independencia", "aviso",
            "La carpeta está en el mismo dispositivo que la aplicación: una falla del disco la perdería junto "
            "con los datos. Use un volumen o destino externo para cumplir el almacenamiento separado."))

    resultado["apto"] = not any(v["nivel"] == "error" for v in verificaciones)
    return resultado


def preparar_almacenamiento(config, tamano_referencia=0):
    """Crea y valida RESPALDO_DIR; devuelve su ruta real o lanza AlmacenamientoNoValido."""
    evaluacion = evaluar_almacenamiento(config, crear=True, tamano_referencia=tamano_referencia)
    if not evaluacion["apto"]:
        errores = [v["mensaje"] for v in evaluacion["verificaciones"] if v["nivel"] == "error"]
        raise AlmacenamientoNoValido(errores[-1] if errores else "El almacenamiento de respaldos no es válido.")
    return _real(config.directorio)


# ---------------------------------------------------------------------------
# Bloqueo entre procesos y modo mantenimiento
# ---------------------------------------------------------------------------

class _Bloqueo:
    """Bloqueo exclusivo no bloqueante sobre un archivo, válido entre procesos."""

    def __init__(self, ruta):
        self.ruta = ruta
        self._fd = None

    def __enter__(self):
        fd = os.open(self.ruta, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as error:
            os.close(fd)
            if fcntl is not None and not isinstance(error, BlockingIOError):
                raise
            raise OperacionEnCurso("Ya hay un respaldo o una restauración en curso. Intente nuevamente al terminar.")
        self._fd = fd
        return self

    def __exit__(self, *excepcion):
        try:
            if fcntl is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            else:
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(self._fd)
            self._fd = None
        return False


def restauracion_en_curso():
    """True mientras una restauración reemplaza los datos.

    La usa app.py para responder 503 al resto de la API durante ese lapso. El
    marcador solo vale si alguien conserva el bloqueo: si el proceso murió a
    medias, el marcador queda huérfano y se ignora.
    """
    directorio = (os.getenv("RESPALDO_DIR") or "").strip()
    if not directorio:
        return False
    marcador = os.path.join(directorio, ARCHIVO_MANTENIMIENTO)
    if not os.path.exists(marcador):
        return False
    try:
        with _Bloqueo(os.path.join(directorio, ARCHIVO_BLOQUEO)):
            return False
    except OperacionEnCurso:
        return True
    except OSError:
        return False


@contextmanager
def _modo_mantenimiento(directorio):
    marcador = os.path.join(directorio, ARCHIVO_MANTENIMIENTO)
    with open(marcador, "w", encoding="utf-8") as archivo:
        json.dump({"pid": os.getpid(), "desde": datetime.now(timezone.utc).isoformat()}, archivo)
    try:
        yield
    finally:
        try:
            os.remove(marcador)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Herramientas de MySQL
# ---------------------------------------------------------------------------

def _entorno_minimo():
    claves = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "LANG", "LC_ALL")
    return {clave: os.environ[clave] for clave in claves if clave in os.environ}


def _escapar_opcion(valor):
    return valor.replace("\\", "\\\\").replace('"', '\\"')


@contextmanager
def _archivo_opciones(host, puerto, usuario, clave):
    """Archivo de opciones [client] temporal (0600) para mysqldump."""
    carpeta = tempfile.mkdtemp(prefix="nahan-opciones-")
    try:
        ruta = os.path.join(carpeta, "cliente.cnf")
        descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            archivo.write(
                "[client]\n"
                f'host="{_escapar_opcion(host)}"\n'
                f"port={puerto}\n"
                f'user="{_escapar_opcion(usuario)}"\n'
                f'password="{_escapar_opcion(clave)}"\n'
            )
        yield ruta
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def _resumir_error(texto):
    """Primera línea útil de la salida de error de una herramienta, acotada."""
    for linea in (texto or "").splitlines():
        linea = linea.strip()
        if linea and "Using a password on the command line" not in linea:
            return linea[:300]
    return "sin detalle"


def _volcar_base(config, ruta_sql):
    """Ejecuta mysqldump sobre la base activa y escribe el volcado en `ruta_sql`."""
    usuario, clave = config.credenciales_respaldo
    _validar_conexion(config.db_host, config.db_port, usuario, clave, config.db_nombre)

    with _archivo_opciones(config.db_host, config.db_port, usuario, clave) as opciones:
        argumentos = [
            config.mysqldump,
            f"--defaults-file={opciones}",
            "--single-transaction",
            "--no-tablespaces",
            "--hex-blob",
            "--complete-insert",
            "--skip-extended-insert",
            "--skip-add-locks",
            "--set-gtid-purged=OFF",
            "--default-character-set=utf8mb4",
            *[f"--ignore-table={config.db_nombre}.{tabla}" for tabla in TABLAS_EXCLUIDAS],
            config.db_nombre,
        ]
        try:
            with open(ruta_sql, "wb") as salida:
                proceso = subprocess.run(
                    argumentos, stdin=subprocess.DEVNULL, stdout=salida, stderr=subprocess.PIPE,
                    timeout=config.timeout, env=_entorno_minimo(), check=False,
                )
        except FileNotFoundError:
            raise ErrorRespaldo("No se encontró mysqldump en el servidor (variable MYSQLDUMP_BIN).")
        except subprocess.TimeoutExpired:
            raise ErrorRespaldo(f"mysqldump superó el tiempo máximo de {config.timeout} segundos.")

    if proceso.returncode != 0:
        logger.error("mysqldump terminó con código %s: %s", proceso.returncode,
                     proceso.stderr.decode("utf-8", "replace")[:2000])
        raise ErrorRespaldo(
            f"mysqldump falló (código {proceso.returncode}): {_resumir_error(proceso.stderr.decode('utf-8', 'replace'))}")


# ---------------------------------------------------------------------------
# Lectura del volcado
# ---------------------------------------------------------------------------

_PATRON_CABECERA = re.compile(
    r"^/\*![0-9]{5} (SET [^;]*|ALTER TABLE `[A-Za-z0-9_]+` (DISABLE|ENABLE) KEYS) \*/;$")
_PATRON_DROP = re.compile(r"^DROP TABLE IF EXISTS `([A-Za-z0-9_]+)`;$")
_PATRON_CREATE = re.compile(r"^CREATE TABLE `([A-Za-z0-9_]+)` \($")
_PATRON_INSERT = re.compile(r"^INSERT INTO `([A-Za-z0-9_]+)` \(")
_PATRON_FIN_CREATE = re.compile(r"^\)[^;]*;$")
_MARCA_FIN_VOLCADO = "-- Dump completed"


def sentencias_del_volcado(ruta_sql):
    """Recorre un volcado de mysqldump y entrega (tipo, tabla, sentencia).

    Solo admite lo que genera este módulo: cabeceras `/*!NNNNN SET ... */`,
    DROP TABLE IF EXISTS, CREATE TABLE e INSERT de una fila por línea
    (--skip-extended-insert). Cualquier otra cosa lanza RespaldoNoValido: un
    esquema con triggers o rutinas, por ejemplo, hace fallar el respaldo en
    lugar de producir un paquete que la restauración no podría reproducir.
    También exige la marca final «-- Dump completed», que mysqldump solo
    escribe cuando terminó bien.
    """
    completo = False
    buffer = None
    tabla_creada = None

    with open(ruta_sql, "r", encoding="utf-8") as archivo:
        for numero, linea in enumerate(archivo, start=1):
            linea = linea.rstrip("\n").rstrip("\r")

            if buffer is not None:
                buffer.append(linea)
                if _PATRON_FIN_CREATE.match(linea):
                    yield "CREATE", tabla_creada, "\n".join(buffer)
                    buffer = None
                elif not linea.startswith("  "):
                    raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: línea {numero} del volcado no admitida.")
                continue

            if not linea.strip():
                continue
            if linea.startswith("--"):
                if linea.startswith(_MARCA_FIN_VOLCADO):
                    completo = True
                continue
            if completo:
                raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: hay contenido después del fin del volcado.")

            if _PATRON_CABECERA.match(linea):
                yield "CABECERA", None, linea
                continue
            coincidencia = _PATRON_DROP.match(linea)
            if coincidencia:
                yield "DROP", coincidencia.group(1), linea
                continue
            coincidencia = _PATRON_CREATE.match(linea)
            if coincidencia:
                tabla_creada = coincidencia.group(1)
                buffer = [linea]
                continue
            coincidencia = _PATRON_INSERT.match(linea)
            if coincidencia and linea.endswith(");"):
                yield "INSERT", coincidencia.group(1), linea
                continue

            raise RespaldoNoValido(
                f"{_MENSAJE_RESPALDO_INVALIDO}: la línea {numero} del volcado contiene una sentencia no admitida "
                "(por ejemplo triggers o rutinas, que este respaldo no soporta).")

    if buffer is not None or not completo:
        raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: el volcado está incompleto.")


def resumir_volcado(ruta_sql):
    """{tabla: filas} del volcado, con la lista de tablas definidas."""
    tablas = {}
    for tipo, tabla, _ in sentencias_del_volcado(ruta_sql):
        if tipo == "CREATE":
            tablas.setdefault(tabla, 0)
        elif tipo == "INSERT":
            tablas[tabla] = tablas.get(tabla, 0) + 1
    if not tablas:
        raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: el volcado no define ninguna tabla.")
    return tablas


# ---------------------------------------------------------------------------
# Paquete .zip
# ---------------------------------------------------------------------------

def _sha256_archivo(ruta):
    huella = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(BLOQUE), b""):
            huella.update(bloque)
    return huella.hexdigest()


def _nombre_miembro_valido(nombre):
    if nombre in (MIEMBRO_MANIFIESTO, MIEMBRO_SQL):
        return True
    if not nombre.startswith(PREFIJO_ADJUNTOS):
        return False
    return _ruta_relativa_valida(nombre[len(PREFIJO_ADJUNTOS):])


def _ruta_relativa_valida(relativa):
    if not relativa or len(relativa) > 400 or "\\" in relativa or "\x00" in relativa:
        return False
    return all(PATRON_COMPONENTE.match(parte) for parte in relativa.split("/"))


def _listar_adjuntos(directorio):
    """([(ruta absoluta, ruta relativa)], [omitidos]) de los adjuntos respaldables.

    No sigue enlaces simbólicos ni incluye archivos ocultos o con nombres que la
    restauración rechazaría; los omitidos se informan para que no pasen
    inadvertidos.
    """
    archivos, omitidos = [], []
    if not os.path.isdir(directorio):
        return archivos, omitidos
    base = os.path.realpath(directorio)
    for carpeta, subcarpetas, nombres in os.walk(base, followlinks=False):
        subcarpetas[:] = sorted(
            s for s in subcarpetas if not os.path.islink(os.path.join(carpeta, s)) and PATRON_COMPONENTE.match(s))
        for nombre in sorted(nombres):
            absoluta = os.path.join(carpeta, nombre)
            relativa = os.path.relpath(absoluta, base).replace(os.sep, "/")
            if os.path.islink(absoluta) or not os.path.isfile(absoluta) or not _ruta_relativa_valida(relativa):
                omitidos.append(relativa)
                continue
            archivos.append((absoluta, relativa))
    return archivos, omitidos


def _escribir_miembro(zf, nombre, origen, limite_restante):
    """Copia `origen` al paquete en bloques; devuelve (sha256, bytes)."""
    info = zipfile.ZipInfo(nombre, date_time=time.localtime()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    huella = hashlib.sha256()
    total = 0
    with open(origen, "rb") as entrada, zf.open(info, "w", force_zip64=True) as salida:
        for bloque in iter(lambda: entrada.read(BLOQUE), b""):
            total += len(bloque)
            if total > limite_restante:
                raise ErrorRespaldo("El respaldo supera el tamaño máximo permitido (RESPALDO_MAX_MB).")
            huella.update(bloque)
            salida.write(bloque)
    return huella.hexdigest(), total


def _migraciones_aplicadas():
    """Números de las migraciones reflejadas en la base, o None si no se pudo saber."""
    ruta = os.path.join(RAIZ_PROYECTO, "database", "migrar.py")
    if not os.path.isfile(ruta):
        return None
    connection = None
    cursor = None
    try:
        especificacion = importlib_util.spec_from_file_location("nahan_migrar", ruta)
        migrar = importlib_util.module_from_spec(especificacion)
        especificacion.loader.exec_module(migrar)
        connection = get_connection()
        if connection is None:
            return None
        cursor = connection.cursor()
        return [numero for numero, _, _ in migrar.migraciones() if migrar.aplicada(cursor, numero)]
    except Exception:
        logger.warning("No se pudo determinar las migraciones aplicadas para el manifiesto")
        return None
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def _migraciones_conocidas():
    ruta = os.path.join(RAIZ_PROYECTO, "database", "migrar.py")
    if not os.path.isfile(ruta):
        return None
    especificacion = importlib_util.spec_from_file_location("nahan_migrar", ruta)
    migrar = importlib_util.module_from_spec(especificacion)
    especificacion.loader.exec_module(migrar)
    return [numero for numero, _, _ in migrar.migraciones()]


def _version_mysqldump(config):
    try:
        salida = subprocess.run([config.mysqldump, "--version"], capture_output=True, timeout=10,
                                env=_entorno_minimo(), check=False)
        return salida.stdout.decode("utf-8", "replace").strip()[:120]
    except (OSError, subprocess.SubprocessError):
        return None


def _construir_paquete(config, tipo, ruta_zip, carpeta_trabajo):
    """Genera el volcado y arma el paquete en `ruta_zip`. Devuelve el manifiesto."""
    ruta_sql = os.path.join(carpeta_trabajo, MIEMBRO_SQL)
    _volcar_base(config, ruta_sql)
    tablas = resumir_volcado(ruta_sql)

    adjuntos, omitidos = _listar_adjuntos(config.directorio_adjuntos)
    total = 0
    descriptor = os.open(ruta_zip, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as destino, \
            zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        sha_sql, bytes_sql = _escribir_miembro(zf, MIEMBRO_SQL, ruta_sql, config.limite_bytes)
        total += bytes_sql
        archivos = {}
        for absoluta, relativa in adjuntos:
            try:
                sha, tamano = _escribir_miembro(zf, PREFIJO_ADJUNTOS + relativa, absoluta, config.limite_bytes - total)
            except FileNotFoundError:
                omitidos.append(relativa)
                continue
            total += tamano
            archivos[relativa] = {"sha256": sha, "bytes": tamano}

        manifiesto = {
            "formato": FORMATO_RESPALDO,
            "aplicacion": APLICACION,
            "creado_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tipo": tipo,
            "herramienta": _version_mysqldump(config),
            "migraciones": _migraciones_aplicadas(),
            "base_de_datos": {
                "archivo": MIEMBRO_SQL,
                "sha256": sha_sql,
                "bytes": bytes_sql,
                "tablas": tablas,
                "excluidas": list(TABLAS_EXCLUIDAS),
            },
            "adjuntos": {"cantidad": len(archivos), "archivos": archivos, "omitidos": sorted(omitidos)},
        }
        zf.writestr(MIEMBRO_MANIFIESTO, json.dumps(manifiesto, ensure_ascii=False, indent=2, sort_keys=True))
    return manifiesto


def _validar_manifiesto(manifiesto):
    try:
        if not isinstance(manifiesto, dict) or manifiesto["formato"] != FORMATO_RESPALDO \
                or manifiesto["aplicacion"] != APLICACION:
            raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: no es un respaldo de esta aplicación o su formato no es compatible.")
        base = manifiesto["base_de_datos"]
        if base["archivo"] != MIEMBRO_SQL or not PATRON_SHA256.match(str(base["sha256"])) \
                or not isinstance(base["bytes"], int) or base["bytes"] < 0:
            raise ValueError("base_de_datos")
        tablas = base["tablas"]
        if not isinstance(tablas, dict) or not tablas or any(
                not PATRON_IDENTIFICADOR.match(str(t)) or isinstance(n, bool) or not isinstance(n, int) or n < 0
                for t, n in tablas.items()):
            raise ValueError("tablas")
        archivos = manifiesto["adjuntos"]["archivos"]
        if not isinstance(archivos, dict) or any(
                not _ruta_relativa_valida(str(r)) or not PATRON_SHA256.match(str(d.get("sha256")))
                or isinstance(d.get("bytes"), bool) or not isinstance(d.get("bytes"), int) or d["bytes"] < 0
                for r, d in archivos.items()):
            raise ValueError("adjuntos")
        migraciones = manifiesto.get("migraciones")
        if migraciones is not None and (
                not isinstance(migraciones, list) or any(not re.fullmatch(r"[0-9]{3}", str(m)) for m in migraciones)):
            raise ValueError("migraciones")
    except RespaldoNoValido:
        raise
    except (KeyError, TypeError, ValueError, AttributeError):
        raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: el manifiesto está incompleto o dañado.")
    return manifiesto


def _copiar_miembro(zf, info, destino, esperado_bytes, esperado_sha, limite_restante):
    """Extrae un miembro comprobando tamaño y huella contra el manifiesto."""
    huella = hashlib.sha256()
    total = 0
    descriptor = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as salida, zf.open(info) as entrada:
        for bloque in iter(lambda: entrada.read(BLOQUE), b""):
            total += len(bloque)
            if total > info.file_size or total > limite_restante:
                raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: un archivo supera el tamaño declarado.")
            huella.update(bloque)
            salida.write(bloque)
    if total != esperado_bytes or huella.hexdigest() != esperado_sha:
        raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: el contenido de «{info.filename}» no coincide con el manifiesto.")


def _verificar_miembro(zf, info, esperado_bytes, esperado_sha, limite_restante):
    huella = hashlib.sha256()
    total = 0
    with zf.open(info) as entrada:
        for bloque in iter(lambda: entrada.read(BLOQUE), b""):
            total += len(bloque)
            if total > info.file_size or total > limite_restante:
                raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: un archivo supera el tamaño declarado.")
            huella.update(bloque)
    if total != esperado_bytes or huella.hexdigest() != esperado_sha:
        raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: el contenido de «{info.filename}» no coincide con el manifiesto.")


def abrir_paquete(ruta, config, sha256_esperado=None, extraer_en=None):
    """Valida un paquete y, si se pide, lo extrae. Devuelve el manifiesto.

    Comprueba, en este orden: archivo regular (no enlace), huella SHA-256 del
    paquete contra la registrada por el sistema, estructura del .zip, nombres
    de los miembros (sin rutas absolutas ni «..», sin enlaces simbólicos ni
    cifrado), límites de tamaño, manifiesto, y huella y tamaño de cada pieza.
    Con `extraer_en` deja `base_de_datos.sql` y `adjuntos/` en esa carpeta
    (privada) en el mismo recorrido, de modo que lo que se restaura es
    exactamente lo que se verificó. Sin ella, igual extrae el volcado a una
    carpeta temporal para recorrerlo completo: debe contener solo sentencias
    admitidas y las mismas tablas y filas que declara el manifiesto.
    """
    try:
        estado = os.lstat(ruta)
    except OSError:
        raise RespaldoNoEncontrado("El archivo del respaldo no está disponible en el almacenamiento.")
    if not stat.S_ISREG(estado.st_mode) or estado.st_size == 0:
        raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: el archivo no es un paquete regular.")
    if sha256_esperado is not None and _sha256_archivo(ruta) != sha256_esperado:
        raise RespaldoNoValido(
            f"{_MENSAJE_RESPALDO_INVALIDO}: la huella SHA-256 no coincide con la registrada (archivo modificado o dañado).")

    temporal = None
    carpeta_sql = extraer_en
    if carpeta_sql is None:
        temporal = carpeta_sql = tempfile.mkdtemp(prefix=PREFIJO_TRABAJO, dir=os.path.dirname(os.path.abspath(ruta)))
    try:
        with zipfile.ZipFile(ruta, "r") as zf:
            miembros = zf.infolist()
            if len(miembros) > MAXIMO_MIEMBROS:
                raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: demasiados archivos.")
            vistos = set()
            total = 0
            for info in miembros:
                modo = info.external_attr >> 16
                if (info.filename in vistos or info.is_dir() or not _nombre_miembro_valido(info.filename)
                        or info.flag_bits & 0x1 or stat.S_IFMT(modo) not in (0, stat.S_IFREG)
                        or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: contiene un elemento no permitido.")
                vistos.add(info.filename)
                total += info.file_size
            if total > config.limite_bytes:
                raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: el contenido supera el límite permitido.")
            if MIEMBRO_MANIFIESTO not in vistos or MIEMBRO_SQL not in vistos:
                raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: faltan el manifiesto o el volcado de la base de datos.")

            info_manifiesto = zf.getinfo(MIEMBRO_MANIFIESTO)
            if info_manifiesto.file_size > 5 * BLOQUE:
                raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: el manifiesto es demasiado grande.")
            try:
                manifiesto = json.loads(zf.read(info_manifiesto).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: el manifiesto no se puede leer.")
            _validar_manifiesto(manifiesto)

            esperados = {PREFIJO_ADJUNTOS + r for r in manifiesto["adjuntos"]["archivos"]}
            if vistos != esperados | {MIEMBRO_MANIFIESTO, MIEMBRO_SQL}:
                raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: el contenido no coincide con el manifiesto.")

            restante = config.limite_bytes
            for info in miembros:
                if info.filename == MIEMBRO_MANIFIESTO:
                    continue
                if info.filename == MIEMBRO_SQL:
                    esperado = manifiesto["base_de_datos"]
                    destino = os.path.join(carpeta_sql, MIEMBRO_SQL)
                else:
                    relativa = info.filename[len(PREFIJO_ADJUNTOS):]
                    esperado = manifiesto["adjuntos"]["archivos"][relativa]
                    destino = os.devnull
                    if extraer_en:
                        destino = os.path.join(extraer_en, *info.filename.split("/"))
                        os.makedirs(os.path.dirname(destino), mode=0o700, exist_ok=True)
                if destino == os.devnull:
                    _verificar_miembro(zf, info, esperado["bytes"], esperado["sha256"], restante)
                else:
                    _copiar_miembro(zf, info, destino, esperado["bytes"], esperado["sha256"], restante)
                restante -= info.file_size

            if resumir_volcado(os.path.join(carpeta_sql, MIEMBRO_SQL)) != manifiesto["base_de_datos"]["tablas"]:
                raise RespaldoNoValido(
                    f"{_MENSAJE_RESPALDO_INVALIDO}: las tablas del volcado no coinciden con el manifiesto.")
    except zipfile.BadZipFile:
        raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: el archivo está dañado o no es un paquete .zip.")
    except (zlib.error, EOFError, NotImplementedError):
        raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: el contenido del paquete está dañado.")
    finally:
        if temporal:
            shutil.rmtree(temporal, ignore_errors=True)
    return manifiesto


def resolver_paquete(config, nombre):
    """Ruta real de un paquete de RESPALDO_DIR, a partir del nombre registrado."""
    if not isinstance(nombre, str) or not PATRON_NOMBRE_PAQUETE.match(nombre):
        raise RespaldoNoEncontrado("El respaldo no tiene un archivo asociado.")
    directorio = _real(config.directorio)
    ruta = os.path.join(directorio, nombre)
    if os.path.islink(ruta) or os.path.dirname(_real(ruta)) != directorio:
        raise RespaldoNoValido(f"{_MENSAJE_RESPALDO_INVALIDO}: la ubicación del archivo no es segura.")
    return ruta


# ---------------------------------------------------------------------------
# Historial (tabla `respaldo`)
# ---------------------------------------------------------------------------

def _recortar(texto, largo=500):
    return texto[:largo] if texto else None


class RegistroMySQL:
    """Lee y escribe el historial de respaldos en la tabla `respaldo`.

    Cada método usa su propia conexión con commit inmediato: el historial debe
    quedar escrito aunque la operación que describe falle después. Con
    `tolerante=True` un fallo del historial se registra en el log y no
    interrumpe la operación (restauración sobre una base vacía, por ejemplo,
    donde la tabla todavía no existe).
    """

    def __init__(self, tolerante=False):
        self.tolerante = tolerante

    @contextmanager
    def _cursor(self):
        connection = get_connection()
        if connection is None:
            raise ErrorRespaldo("No se pudo conectar a la base de datos para registrar el respaldo.")
        cursor = connection.cursor(dictionary=True)
        try:
            yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

    def _intentar(self, funcion, por_defecto=None):
        try:
            return funcion()
        except ErrorRespaldo:
            if not self.tolerante:
                raise
        except Exception:
            logger.warning("No se pudo acceder al historial de respaldos", exc_info=True)
            if not self.tolerante:
                raise ErrorRespaldo("No se pudo acceder al historial de respaldos.")
        return por_defecto

    def iniciar(self, operacion, tipo, id_usuario=None, id_relacionado=None):
        def accion():
            with self._cursor() as cursor:
                cursor.execute(
                    "INSERT INTO respaldo (operacion, tipo, estado, id_usuario, id_relacionado) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (operacion, tipo, ESTADO_EN_CURSO, id_usuario, id_relacionado),
                )
                return cursor.lastrowid
        return self._intentar(accion)

    def finalizar(self, id_respaldo, estado, duracion, nombre_archivo=None, tamano_bytes=None,
                  sha256=None, detalle=None, mensaje_error=None):
        if id_respaldo is None:
            return

        def accion():
            with self._cursor() as cursor:
                cursor.execute(
                    "UPDATE respaldo SET estado = %s, fecha_fin = NOW(), duracion_segundos = %s, "
                    "nombre_archivo = %s, tamano_bytes = %s, sha256 = %s, detalle = %s, mensaje_error = %s "
                    "WHERE id_respaldo = %s",
                    (estado, round(duracion, 2), nombre_archivo, tamano_bytes, sha256,
                     _recortar(detalle), _recortar(mensaje_error), id_respaldo),
                )
        self._intentar(accion)

    def obtener(self, id_respaldo):
        def accion():
            with self._cursor() as cursor:
                cursor.execute("SELECT * FROM respaldo WHERE id_respaldo = %s", (id_respaldo,))
                return cursor.fetchone()
        return self._intentar(accion)

    def listar(self, limite):
        def accion():
            with self._cursor() as cursor:
                cursor.execute(
                    """
                    SELECT r.id_respaldo, r.operacion, r.tipo, r.estado, r.fecha_inicio, r.fecha_fin,
                           r.duracion_segundos, r.id_usuario, u.nombres AS usuario, r.id_relacionado,
                           r.nombre_archivo, r.tamano_bytes, r.sha256, r.detalle, r.mensaje_error,
                           r.archivo_eliminado_en
                    FROM respaldo r
                    LEFT JOIN usuario u ON u.id_usuario = r.id_usuario
                    ORDER BY r.fecha_inicio DESC, r.id_respaldo DESC
                    LIMIT %s
                    """,
                    (limite,),
                )
                return cursor.fetchall()
        return self._intentar(accion, [])

    def ultimo_exitoso(self, operacion=OPERACION_RESPALDO):
        def accion():
            with self._cursor() as cursor:
                cursor.execute(
                    "SELECT id_respaldo, tipo, fecha_inicio, fecha_fin, tamano_bytes FROM respaldo "
                    "WHERE operacion = %s AND estado = %s ORDER BY fecha_inicio DESC, id_respaldo DESC LIMIT 1",
                    (operacion, ESTADO_EXITOSO),
                )
                return cursor.fetchone()
        return self._intentar(accion)

    def hay_en_curso(self):
        def accion():
            with self._cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS n FROM respaldo WHERE estado = %s", (ESTADO_EN_CURSO,))
                return cursor.fetchone()["n"] > 0
        return self._intentar(accion, False)

    def cerrar_huerfanos(self):
        """Marca como fallidas las operaciones EN_CURSO que ningún proceso sigue ejecutando.

        Solo se llama con el bloqueo exclusivo en mano: si alguien lo tuviera, no
        estaríamos aquí, así que todo lo que figure EN_CURSO quedó a medias
        (proceso terminado por el sistema, corte de energía, tiempo agotado).
        """
        def accion():
            with self._cursor() as cursor:
                cursor.execute(
                    "UPDATE respaldo SET estado = %s, fecha_fin = NOW(), "
                    "mensaje_error = 'Interrumpido: el proceso terminó antes de completar la operación.' "
                    "WHERE estado = %s",
                    (ESTADO_FALLIDO, ESTADO_EN_CURSO),
                )
        self._intentar(accion)

    def sobrantes(self, conservar):
        """Respaldos exitosos con archivo que exceden `conservar`, del más antiguo al más nuevo."""
        def accion():
            with self._cursor() as cursor:
                cursor.execute(
                    "SELECT id_respaldo, nombre_archivo FROM respaldo "
                    "WHERE operacion = %s AND estado = %s AND archivo_eliminado_en IS NULL "
                    "AND nombre_archivo IS NOT NULL ORDER BY fecha_inicio DESC, id_respaldo DESC",
                    (OPERACION_RESPALDO, ESTADO_EXITOSO),
                )
                return list(reversed(cursor.fetchall()[conservar:]))
        return self._intentar(accion, [])

    def marcar_archivo_eliminado(self, id_respaldo):
        def accion():
            with self._cursor() as cursor:
                cursor.execute("UPDATE respaldo SET archivo_eliminado_en = NOW() WHERE id_respaldo = %s",
                               (id_respaldo,))
        self._intentar(accion)


# ---------------------------------------------------------------------------
# Respaldo
# ---------------------------------------------------------------------------

def _limpiar_restos(directorio):
    """Borra trabajos y paquetes parciales que dejó una ejecución interrumpida.

    Se llama con el bloqueo exclusivo en mano, así que nada de esto está en uso.
    """
    for nombre in os.listdir(directorio):
        if nombre.startswith(PREFIJO_TRABAJO):
            shutil.rmtree(os.path.join(directorio, nombre), ignore_errors=True)
        elif nombre.startswith(PREFIJO_PARCIAL):
            try:
                os.remove(os.path.join(directorio, nombre))
            except OSError:
                pass


def _nombre_nuevo_paquete():
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"nahan-respaldo-{marca}-{secrets.token_hex(4)}.zip"


def _describir(manifiesto, tamano):
    tablas = manifiesto["base_de_datos"]["tablas"]
    adjuntos = manifiesto["adjuntos"]
    texto = f"tablas={len(tablas)}, filas={sum(tablas.values())}, adjuntos={adjuntos['cantidad']}"
    if adjuntos["omitidos"]:
        texto += f", adjuntos_omitidos={len(adjuntos['omitidos'])}"
    return f"{texto}, paquete={tamano} bytes"


def _respaldar(config, registro, tipo, id_usuario=None, id_relacionado=None):
    """Un respaldo completo con el bloqueo ya tomado. Devuelve el resultado o lanza ErrorRespaldo."""
    inicio = time.monotonic()
    id_respaldo = registro.iniciar(OPERACION_RESPALDO, tipo, id_usuario, id_relacionado)
    carpeta_trabajo = None
    parcial = None
    try:
        directorio = preparar_almacenamiento(config, tamano_referencia=_tamano_ultimo(registro))
        carpeta_trabajo = tempfile.mkdtemp(prefix=PREFIJO_TRABAJO, dir=directorio)
        nombre = _nombre_nuevo_paquete()
        parcial = os.path.join(directorio, f"{PREFIJO_PARCIAL}{secrets.token_hex(4)}.zip")
        manifiesto = _construir_paquete(config, tipo, parcial, carpeta_trabajo)

        # Se vuelve a abrir como lo haría una restauración: un paquete que no se
        # puede verificar no cuenta como respaldo.
        abrir_paquete(parcial, config)
        sha256 = _sha256_archivo(parcial)
        tamano = os.path.getsize(parcial)
        with open(parcial, "rb") as archivo:
            os.fsync(archivo.fileno())
        final = os.path.join(directorio, nombre)
        os.replace(parcial, final)
        parcial = None
        _escribir_huella(final, sha256)

        detalle = _describir(manifiesto, tamano)
        registro.finalizar(id_respaldo, ESTADO_EXITOSO, time.monotonic() - inicio, nombre, tamano, sha256, detalle)
        logger.info("Respaldo %s %s completado: %s", id_respaldo, tipo, detalle)
        return {"id_respaldo": id_respaldo, "nombre_archivo": nombre, "tamano_bytes": tamano,
                "sha256": sha256, "detalle": detalle, "manifiesto": manifiesto}
    except ErrorRespaldo as error:
        registro.finalizar(id_respaldo, ESTADO_FALLIDO, time.monotonic() - inicio, mensaje_error=error.mensaje)
        error.id_respaldo = id_respaldo
        raise
    except Exception as error:
        logger.exception("Error inesperado durante el respaldo")
        registro.finalizar(id_respaldo, ESTADO_FALLIDO, time.monotonic() - inicio,
                           mensaje_error=f"Error inesperado ({type(error).__name__}). Revise el registro del servidor.")
        fallo = ErrorRespaldo("Error inesperado durante el respaldo.")
        fallo.id_respaldo = id_respaldo
        raise fallo
    finally:
        if parcial and os.path.exists(parcial):
            try:
                os.remove(parcial)
            except OSError:
                pass
        if carpeta_trabajo:
            shutil.rmtree(carpeta_trabajo, ignore_errors=True)


def _escribir_huella(ruta_paquete, sha256):
    """Deja la huella junto al paquete: referencia de integridad que no depende de la base de datos."""
    descriptor = os.open(ruta_paquete + ".sha256", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
        archivo.write(f"{sha256}  {os.path.basename(ruta_paquete)}\n")


def _leer_huella(ruta_paquete):
    try:
        with open(ruta_paquete + ".sha256", "r", encoding="utf-8") as archivo:
            huella = archivo.read().split()[0]
    except (OSError, IndexError):
        return None
    return huella if PATRON_SHA256.match(huella) else None


def _tamano_ultimo(registro):
    ultimo = registro.ultimo_exitoso()
    return int(ultimo["tamano_bytes"] or 0) if ultimo else 0


def _aplicar_retencion(config, registro, directorio):
    """Elimina los paquetes más antiguos que superen RESPALDO_RETENCION_MAXIMA."""
    for fila in registro.sobrantes(config.retencion_maxima):
        nombre = fila["nombre_archivo"]
        if not PATRON_NOMBRE_PAQUETE.match(nombre or ""):
            continue
        try:
            os.remove(os.path.join(directorio, nombre))
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("No se pudo eliminar el respaldo antiguo %s", nombre)
            continue
        try:
            os.remove(os.path.join(directorio, nombre + ".sha256"))
        except OSError:
            pass
        registro.marcar_archivo_eliminado(fila["id_respaldo"])


def ejecutar_respaldo(tipo, id_usuario=None, config=None, registro=None):
    """Hace un respaldo completo. `tipo` es MANUAL o PROGRAMADO.

    Lanza OperacionEnCurso si hay otro respaldo o restauración activo, y
    ErrorRespaldo (con `id_respaldo`) si el intento falla; en ambos casos el
    intento queda en el historial salvo que no se haya llegado a empezar.
    """
    if tipo not in (TIPO_MANUAL, TIPO_PROGRAMADO):
        raise ErrorRespaldo("El tipo de respaldo no es válido.")
    config = config or ConfigRespaldo()
    registro = registro or RegistroMySQL()

    try:
        directorio = preparar_almacenamiento(config)
    except AlmacenamientoNoValido as error:
        # Sin carpeta no hay bloqueo posible, pero el intento debe quedar a la vista.
        id_respaldo = registro.iniciar(OPERACION_RESPALDO, tipo, id_usuario)
        registro.finalizar(id_respaldo, ESTADO_FALLIDO, 0, mensaje_error=error.mensaje)
        error.id_respaldo = id_respaldo
        raise

    with _Bloqueo(os.path.join(directorio, ARCHIVO_BLOQUEO)):
        registro.cerrar_huerfanos()
        _limpiar_restos(directorio)
        resultado = _respaldar(config, registro, tipo, id_usuario)
        try:
            _aplicar_retencion(config, registro, directorio)
        except Exception:
            logger.warning("No se pudo aplicar la política de retención", exc_info=True)
    return resultado


def verificar_respaldo(id_respaldo, config=None, registro=None):
    """Comprueba la integridad de un respaldo sin restaurarlo. Devuelve su resumen."""
    config = config or ConfigRespaldo()
    registro = registro or RegistroMySQL()
    fila = _fila_restaurable(registro, id_respaldo)
    manifiesto = abrir_paquete(resolver_paquete(config, fila["nombre_archivo"]), config, fila["sha256"])
    return _resumen_manifiesto(manifiesto)


def _resumen_manifiesto(manifiesto):
    tablas = manifiesto["base_de_datos"]["tablas"]
    return {
        "creado_utc": manifiesto["creado_utc"],
        "tablas": len(tablas),
        "filas": sum(tablas.values()),
        "adjuntos": manifiesto["adjuntos"]["cantidad"],
        "migraciones": manifiesto.get("migraciones"),
    }


def _fila_restaurable(registro, id_respaldo):
    fila = registro.obtener(id_respaldo)
    if not fila or fila["operacion"] != OPERACION_RESPALDO:
        raise RespaldoNoEncontrado("El respaldo indicado no existe.")
    if fila["estado"] != ESTADO_EXITOSO or not fila["nombre_archivo"]:
        raise RespaldoNoValido("Solo se pueden usar respaldos que terminaron correctamente.")
    if fila["archivo_eliminado_en"] is not None:
        raise RespaldoNoEncontrado("El archivo de este respaldo fue eliminado por la política de retención.")
    return fila


# ---------------------------------------------------------------------------
# Restauración
# ---------------------------------------------------------------------------

def _conectar_restauracion(config):
    import mysql.connector

    usuario, clave = config.credenciales_restauracion
    _validar_conexion(config.db_host, config.db_port, usuario, clave, config.restauracion_db_nombre)
    try:
        return mysql.connector.connect(
            host=config.db_host, port=config.db_port, user=usuario, password=clave,
            database=config.restauracion_db_nombre, charset="utf8mb4", use_unicode=True,
            connection_timeout=10, autocommit=False,
        )
    except mysql.connector.Error as error:
        raise ErrorRespaldo(f"No se pudo conectar a la base de destino (error {error.errno}).")


def _cargar_volcado(config, ruta_sql, tablas_esperadas):
    """Reproduce el volcado en la base de destino y comprueba el conteo de filas."""
    import mysql.connector

    connection = _conectar_restauracion(config)
    cursor = connection.cursor()
    try:
        cursor.execute("SET SESSION foreign_key_checks = 0")
        pendientes = 0
        for tipo, tabla, sentencia in sentencias_del_volcado(ruta_sql):
            cursor.execute(sentencia)
            pendientes += 1
            if tipo == "INSERT" and pendientes >= 500:
                connection.commit()
                pendientes = 0
        connection.commit()

        for tabla, esperadas in tablas_esperadas.items():
            cursor.execute(f"SELECT COUNT(*) FROM `{tabla}`")
            obtenidas = cursor.fetchone()[0]
            if obtenidas != esperadas:
                raise ErrorRespaldo(
                    f"La tabla «{tabla}» quedó con {obtenidas} filas y el respaldo tiene {esperadas}.")
        cursor.execute("SET SESSION foreign_key_checks = 1")
    except mysql.connector.Error as error:
        connection.rollback()
        raise ErrorRespaldo(f"MySQL rechazó el volcado (error {error.errno}).")
    finally:
        cursor.close()
        connection.close()


def _comprobar_privilegios_restauracion(config):
    """Prueba CREATE, INSERT y DROP en la base de destino con una tabla desechable.

    Detectar la falta de privilegios aquí evita empezar una restauración que se
    detendría en la primera sentencia con la base sin tocar pero con un
    respaldo previo ya tomado y una recuperación automática innecesaria.
    """
    import mysql.connector

    connection = _conectar_restauracion(config)
    cursor = connection.cursor()
    try:
        cursor.execute("DROP TABLE IF EXISTS `_nahan_privilegios`")
        cursor.execute("CREATE TABLE `_nahan_privilegios` (id INT)")
        cursor.execute("INSERT INTO `_nahan_privilegios` VALUES (1)")
        cursor.execute("DROP TABLE `_nahan_privilegios`")
        connection.commit()
    except mysql.connector.Error as error:
        raise ErrorRespaldo(
            "La cuenta de restauración no tiene los privilegios necesarios (CREATE, INSERT y DROP) sobre la "
            f"base de destino (error {error.errno}).")
    finally:
        cursor.close()
        connection.close()


def _copiar_adjuntos(origen, destino, archivos):
    """Copia los adjuntos del respaldo sin borrar nada de lo que ya hay."""
    if not archivos:
        return
    os.makedirs(destino, exist_ok=True)
    raiz = _real(destino)
    for relativa in sorted(archivos):
        fuente = os.path.join(origen, PREFIJO_ADJUNTOS.rstrip("/"), *relativa.split("/"))
        objetivo = os.path.join(raiz, *relativa.split("/"))
        if not _dentro_de(objetivo, raiz):
            raise ErrorRespaldo("Un adjunto del respaldo apunta fuera del directorio de adjuntos.")
        os.makedirs(os.path.dirname(objetivo), exist_ok=True)
        temporal = f"{objetivo}.restaurando-{secrets.token_hex(3)}"
        shutil.copyfile(fuente, temporal)
        os.replace(temporal, objetivo)


def _aplicar_paquete(config, ruta_paquete, sha256, carpeta, restaurar_adjuntos):
    manifiesto = abrir_paquete(ruta_paquete, config, sha256, extraer_en=carpeta)
    _cargar_volcado(config, os.path.join(carpeta, MIEMBRO_SQL), manifiesto["base_de_datos"]["tablas"])
    if restaurar_adjuntos:
        _copiar_adjuntos(carpeta, config.directorio_adjuntos, manifiesto["adjuntos"]["archivos"])
    return manifiesto


def _advertencias_de_version(manifiesto):
    """Rechaza respaldos de una versión más nueva; avisa de los más antiguos."""
    del_respaldo = manifiesto.get("migraciones")
    conocidas = _migraciones_conocidas()
    if del_respaldo is None or conocidas is None:
        return ["No se pudo comprobar la versión del esquema del respaldo."]
    desconocidas = sorted(set(del_respaldo) - set(conocidas))
    if desconocidas:
        raise RespaldoNoValido(
            "El respaldo proviene de una versión más nueva de la aplicación "
            f"(migraciones {', '.join(desconocidas)}); actualice la aplicación antes de restaurarlo.")
    faltan = sorted(set(conocidas) - set(del_respaldo))
    if faltan:
        return [f"El respaldo es de un esquema anterior; ejecute database/migrar.py (faltan: {', '.join(faltan)})."]
    return []


def _base_tiene_tablas(config):
    connection = _conectar_restauracion(config)
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() "
            f"AND table_name NOT IN ({', '.join(['%s'] * len(TABLAS_EXCLUIDAS))})",
            TABLAS_EXCLUIDAS,
        )
        return cursor.fetchone()[0] > 0
    finally:
        cursor.close()
        connection.close()


def ejecutar_restauracion(id_respaldo=None, id_usuario=None, config=None, registro=None, nombre_archivo=None):
    """Restaura un respaldo exitoso sobre la base de destino configurada.

    El respaldo se indica por `id_respaldo` (historial) o, para recuperarse de
    la pérdida total de la base —cuando ya no hay historial—, por el nombre del
    paquete en RESPALDO_DIR: en ese caso su integridad se comprueba contra el
    archivo .sha256 que se guardó a su lado y la restauración no queda
    registrada si la tabla `respaldo` todavía no existe.

    El destino lo fija el servidor (RESTAURACION_DB_NAME, o DB_NAME si no se
    define), nunca la solicitud. Si es la base activa, antes de tocarla se
    toma un respaldo PREVIO_RESTAURACION y, si la restauración falla a medias,
    se vuelve a ese estado automáticamente. Nunca se borran adjuntos.
    """
    config = config or ConfigRespaldo()
    registro = registro or RegistroMySQL()

    if not config.restauracion_habilitada:
        raise OperacionNoPermitida(
            "La restauración está deshabilitada en este entorno (RESTAURACION_HABILITADA).")
    if not PATRON_IDENTIFICADOR.match(config.restauracion_db_nombre or ""):
        raise OperacionNoPermitida("La base de destino de la restauración no está configurada correctamente.")

    directorio = preparar_almacenamiento(config)
    if id_respaldo is not None:
        fila = _fila_restaurable(registro, id_respaldo)
    else:
        paquete_directo = resolver_paquete(config, nombre_archivo)
        huella = _leer_huella(paquete_directo)
        if huella is None:
            raise RespaldoNoValido(
                "No se encontró la huella (.sha256) junto al paquete: no se puede comprobar su integridad.")
        fila = {"nombre_archivo": nombre_archivo, "sha256": huella,
                "tamano_bytes": os.path.getsize(paquete_directo)}
    paquete = resolver_paquete(config, fila["nombre_archivo"])
    activa = config.restaura_base_activa

    with _Bloqueo(os.path.join(directorio, ARCHIVO_BLOQUEO)):
        registro.cerrar_huerfanos()
        inicio = time.monotonic()
        id_restauracion = registro.iniciar(OPERACION_RESTAURACION, TIPO_MANUAL, id_usuario, id_respaldo)
        carpeta = previo = None
        modificada = False
        try:
            with _modo_mantenimiento(directorio):
                _limpiar_restos(directorio)
                carpeta = tempfile.mkdtemp(prefix=PREFIJO_TRABAJO, dir=directorio)

                # Validación completa antes de tocar nada.
                manifiesto = abrir_paquete(paquete, config, fila["sha256"], extraer_en=carpeta)
                advertencias = _advertencias_de_version(manifiesto)
                _comprobar_privilegios_restauracion(config)

                if activa and _base_tiene_tablas(config):
                    previo = _respaldar(config, registro, TIPO_PREVIO,
                                        id_usuario=id_usuario, id_relacionado=id_restauracion)
                modificada = True
                _cargar_volcado(config, os.path.join(carpeta, MIEMBRO_SQL), manifiesto["base_de_datos"]["tablas"])
                if activa:
                    _copiar_adjuntos(carpeta, config.directorio_adjuntos, manifiesto["adjuntos"]["archivos"])
                    cuerpo = "adjuntos restaurados sin borrar los existentes"
                else:
                    cuerpo = f"restaurado en «{config.restauracion_db_nombre}»; los adjuntos no se tocaron"

            detalle = f"{cuerpo}; {_describir(manifiesto, int(fila['tamano_bytes'] or 0))}"
            if previo:
                detalle += f"; copia previa={previo['nombre_archivo']}"
            if advertencias:
                detalle += "; " + " ".join(advertencias)
            registro.finalizar(id_restauracion, ESTADO_EXITOSO, time.monotonic() - inicio, detalle=detalle)
            logger.info("Restauración %s del respaldo %s completada", id_restauracion, id_respaldo)
            return {"id_restauracion": id_restauracion, "id_respaldo": id_respaldo, "detalle": detalle,
                    "id_previo": previo["id_respaldo"] if previo else None, "advertencias": advertencias}
        except Exception as error:
            mensaje = error.mensaje if isinstance(error, ErrorRespaldo) else \
                f"Error inesperado ({type(error).__name__})."
            if not isinstance(error, ErrorRespaldo):
                logger.exception("Error inesperado durante la restauración")
            recuperacion = _recuperar(config, previo, modificada, directorio)
            registro.finalizar(id_restauracion, ESTADO_FALLIDO, time.monotonic() - inicio,
                               mensaje_error=f"{mensaje} {recuperacion}".strip())
            fallo = error if isinstance(error, ErrorRespaldo) else ErrorRespaldo(mensaje)
            fallo.id_respaldo = id_restauracion
            fallo.recuperacion = recuperacion
            raise fallo
        finally:
            if carpeta:
                shutil.rmtree(carpeta, ignore_errors=True)


def _recuperar(config, previo, modificada, directorio):
    """Intenta volver al estado anterior cuando una restauración falló después de tocar la base."""
    if not modificada:
        return "La base de datos no fue modificada."
    if not previo:
        return "La base de destino pudo quedar incompleta; vuelva a restaurar un respaldo válido."
    try:
        carpeta_previo = tempfile.mkdtemp(prefix=PREFIJO_TRABAJO, dir=directorio)
        try:
            _aplicar_paquete(config, resolver_paquete(config, previo["nombre_archivo"]), previo["sha256"],
                             carpeta_previo, restaurar_adjuntos=True)
        finally:
            shutil.rmtree(carpeta_previo, ignore_errors=True)
        return "Se restableció automáticamente el estado anterior a la restauración."
    except Exception:
        logger.exception("No se pudo restablecer el estado anterior tras una restauración fallida")
        return (f"No se pudo restablecer automáticamente el estado anterior; restáurelo manualmente desde "
                f"{previo['nombre_archivo']}.")


# ---------------------------------------------------------------------------
# Estado para la interfaz
# ---------------------------------------------------------------------------

def estado_del_sistema(config=None, registro=None):
    config = config or ConfigRespaldo()
    registro = registro or RegistroMySQL(tolerante=True)
    ultimo = registro.ultimo_exitoso()
    evaluacion = evaluar_almacenamiento(config, tamano_referencia=int(ultimo["tamano_bytes"] or 0) if ultimo else 0)
    return {
        "almacenamiento": evaluacion,
        "restauracion_habilitada": config.restauracion_habilitada,
        "base_de_destino": config.restauracion_db_nombre if config.restauracion_habilitada else None,
        "retencion_maxima": config.retencion_maxima,
        "operacion_en_curso": bool(registro.hay_en_curso()),
        "ultimo_exitoso": ultimo,
    }
