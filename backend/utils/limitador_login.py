"""SEC-02 — Límite de intentos fallidos de inicio de sesión.

Cada intento que llega a verificarse reserva una fila en
`intento_login_fallido` ANTES de comprobar la contraseña. La fila representa
un intento que consume cuota: si el login resulta exitoso se borra; si falla
(o el proceso muere a mitad de bcrypt) se conserva. Tres contadores cuentan
esas filas en una ventana móvil de 15 minutos:

    cuenta + IP   5      (adivinación desde una IP)
    cuenta       15      (adivinación distribuida)
    IP           40      (una IP contra muchas cuentas)

Concurrencia. La reserva (contar y, si hay cupo, insertar) es una sección
crítica serializada con un bloqueo con nombre de MySQL (GET_LOCK), válido
entre los workers de Gunicorn. El bloqueo dura unos milisegundos y se libera
antes de bcrypt: nunca se mantiene mientras se verifica la contraseña.
Dentro de la sección:

  0. antes de esperar el bloqueo se termina la transacción de las lecturas
     previas (así no se retienen bloqueos de lectura bajo SERIALIZABLE);
  1. se termina cualquier instantánea anterior (ROLLBACK): en REPEATABLE READ
     el recuento debe ver las filas que otras secciones ya confirmaron;
  2. se cuenta; si algún contador alcanzó su umbral, no se escribe nada;
  3. si hay cupo, se inserta y se confirma ANTES de liberar el bloqueo.

Así cada sección ve todas las reservas anteriores y solo inserta con cupo
libre: en cualquier ventana de 15 minutos hay como máximo N verificaciones
fallidas por contador. Las solicitudes rechazadas no escriben nada, de modo
que no consumen cuota ni alargan un bloqueo.

Errores. Si el limitador no puede conocer el estado de los contadores, el
login de esa solicitud falla cerrado (503); nunca se desactiva en silencio.
Un error inesperado de programación sube como excepción (500 genérico). Solo
la purga es opcional: un error al limpiar se registra como advertencia y no
afecta al login.

Datos. No se guardan contraseñas ni correos: la cuenta se identifica con un
HMAC del correo canónico y la IP se guarda truncada (IPv4 completa, IPv6 a su
prefijo /64). Las filas se purgan pasadas RETENCION_HORAS horas.
"""
import hashlib
import hmac
import ipaddress
import logging
from datetime import datetime, timedelta

import mysql.connector
from flask import current_app, jsonify

logger = logging.getLogger(__name__)

VENTANA_MINUTOS = 15
MAX_POR_PAR = 5        # cuenta + IP
MAX_POR_CUENTA = 15
MAX_POR_IP = 40

RETENCION_HORAS = 24
LOTE_PURGA = 500
CADA_N_RESERVAS_PURGAR = 100

NOMBRE_BLOQUEO_RESERVA = "nahan:login:reserva"
NOMBRE_BLOQUEO_PURGA = "nahan:login:purga"
SEGUNDOS_ESPERA_BLOQUEO = 2
SEGUNDOS_REINTENTO_NO_DISPONIBLE = 5

MENSAJE_LIMITE = "Demasiados intentos fallidos. Espere unos minutos e inténtelo de nuevo."
CODIGO_LIMITE = "DEMASIADOS_INTENTOS"
MENSAJE_NO_DISPONIBLE = (
    "El servicio de inicio de sesión no está disponible temporalmente. "
    "Inténtelo de nuevo en unos segundos."
)
CODIGO_NO_DISPONIBLE = "SERVICIO_NO_DISPONIBLE"

ERRNO_LOCK_WAIT_TIMEOUT = 1205
ERRNO_DEADLOCK = 1213
# Tabla o columna inexistente, tipo o tamaño incorrecto: migración 008 sin
# aplicar, incompleta o aplicada con otra definición.
ERRNOS_ESQUEMA = frozenset({1146, 1054, 1364, 1366, 1265, 1406, 1264})

_SQL_CLAVE_CORREO = (
    "SELECT HEX(WEIGHT_STRING(CAST(%s AS CHAR CHARACTER SET utf8mb4) "
    "COLLATE utf8mb4_unicode_ci)) AS peso"
)
# Peso UCA de U+0020. utf8mb4_unicode_ci es PAD SPACE: `=` ignora los espacios
# finales, pero WEIGHT_STRING los conserva como unidades de este peso.
_UNIDAD_PESO_ESPACIO = "0209"

_VENTANA = f"fecha > DATE_SUB(UTC_TIMESTAMP(), INTERVAL {VENTANA_MINUTOS} MINUTE)"
_SQL_CONTEOS = f"""
    SELECT
        (SELECT COUNT(*) FROM intento_login_fallido
          WHERE clave_cuenta = %s AND ip_cliente = %s AND {_VENTANA}) AS par,
        (SELECT COUNT(*) FROM intento_login_fallido
          WHERE clave_cuenta = %s AND {_VENTANA}) AS cuenta,
        (SELECT COUNT(*) FROM intento_login_fallido
          WHERE ip_cliente = %s AND {_VENTANA}) AS por_ip
"""
_SQL_INSERTAR = (
    "INSERT INTO intento_login_fallido (clave_cuenta, ip_cliente, id_usuario, fecha) "
    "VALUES (%s, %s, %s, UTC_TIMESTAMP())"
)
_SQL_BORRAR_RESERVA = "DELETE FROM intento_login_fallido WHERE id_intento = %s"


class LimiteAlcanzado(Exception):
    """Algún contador alcanzó su umbral. `segundos` es el valor de Retry-After."""

    def __init__(self, segundos):
        super().__init__("límite de intentos de inicio de sesión alcanzado")
        self.segundos = segundos


class LimitadorNoDisponible(Exception):
    """El limitador no pudo determinar el estado de los contadores."""

    def __init__(self, segundos=SEGUNDOS_REINTENTO_NO_DISPONIBLE):
        super().__init__("limitador de inicio de sesión no disponible")
        self.segundos = segundos


# --- Claves ------------------------------------------------------------------

def normalizar_ip(direccion):
    """IP truncada para almacenar, o None si no es fiable.

    IPv4: 4 bytes. IPv6: prefijo /64 (8 bytes). Una dirección ausente,
    inválida o de loopback devuelve None: detrás de un proxy mal configurado
    todos los clientes aparecerían como 127.0.0.1 y limitar por IP o por par
    bloquearía a toda la organización.
    """
    if not direccion:
        return None
    try:
        ip = ipaddress.ip_address(str(direccion).split("%", 1)[0])
    except ValueError:
        return None
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_loopback or ip.is_unspecified:
        return None
    return ip.packed if ip.version == 4 else ip.packed[:8]


def quitar_relleno(peso_hex):
    """Quita del final del peso las unidades de espacio (PAD SPACE)."""
    while len(peso_hex) >= 4 and len(peso_hex) % 4 == 0 and peso_hex.endswith(_UNIDAD_PESO_ESPACIO):
        peso_hex = peso_hex[:-4]
    return peso_hex


def _secreto():
    return hashlib.sha256(b"nahan-login-limit-v1:" + current_app.config["SECRET_KEY"].encode("utf-8")).digest()


def clave_desde_peso(peso_hex, secreto):
    """HMAC-SHA256 (32 bytes) del peso canónico de un correo."""
    canonico = quitar_relleno(peso_hex).encode("ascii")
    return hmac.new(secreto, canonico, hashlib.sha256).digest()


def calcular_clave_cuenta(cursor, email):
    """Clave de cuenta de un correo, igual para cuentas existentes e inexistentes.

    La canonicalización la hace MySQL con el mismo collation que la columna
    `usuario.email` (utf8mb4_unicode_ci), de modo que dos correos que el login
    consideraría la misma cuenta comparten clave y no se pueden usar variantes
    de mayúsculas, acentos o espacios para eludir los contadores.
    """
    try:
        cursor.execute(_SQL_CLAVE_CORREO, (email,))
        fila = cursor.fetchone()
        peso = _valor(fila, "peso", 0)
        if isinstance(peso, (bytes, bytearray)):
            peso = bytes(peso).decode("ascii")
        if not isinstance(peso, str):
            raise LimitadorNoDisponible()
        return clave_desde_peso(peso, _secreto())
    except mysql.connector.Error as error:
        raise _error_no_disponible(error)


# --- Utilidades de acceso a filas ---------------------------------------------

def _valor(fila, nombre, posicion):
    if fila is None:
        return None
    if isinstance(fila, dict):
        return fila.get(nombre)
    return fila[posicion]


def _entero(valor):
    return int(valor) if valor is not None else 0


# --- Errores -----------------------------------------------------------------

def _error_no_disponible(error):
    """Registra un error de MySQL del limitador y devuelve la excepción 503.

    Solo se registra el código de error: el texto de MySQL podría incluir
    valores de las sentencias.
    """
    errno = getattr(error, "errno", None)
    if errno in ERRNOS_ESQUEMA:
        logger.critical(
            "Limitador de login: la tabla intento_login_fallido falta o es incorrecta "
            "(errno %s). Aplique la migración 008 (database/migrar.py). "
            "Los inicios de sesión se rechazan hasta corregirlo.", errno,
        )
    elif errno in (ERRNO_LOCK_WAIT_TIMEOUT, ERRNO_DEADLOCK):
        logger.error("Limitador de login: conflicto de bloqueo persistente (errno %s)", errno)
    else:
        logger.error("Limitador de login: error de base de datos (errno %s)", errno)
    return LimitadorNoDisponible()


def _revertir(connection):
    try:
        connection.rollback()
    except Exception:  # pragma: no cover - conexión ya inutilizable
        logger.warning("Limitador de login: no se pudo revertir la transacción")


# --- Recuento ----------------------------------------------------------------

def _contar(cursor, clave, ip):
    """(par, cuenta, por_ip). Con ip=None los contadores de par y de IP dan 0:
    `ip_cliente = NULL` nunca coincide."""
    cursor.execute(_SQL_CONTEOS, (clave, ip, clave, ip))
    fila = cursor.fetchone()
    return (
        _entero(_valor(fila, "par", 0)),
        _entero(_valor(fila, "cuenta", 1)),
        _entero(_valor(fila, "por_ip", 2)),
    )


def _espera_hasta_cupo(cursor, condicion, parametros, conteo, maximo):
    """Segundos hasta que el contador baje del umbral: expira la fila número
    (conteo - maximo + 1) por antigüedad."""
    cursor.execute(
        f"SELECT fecha, UTC_TIMESTAMP() AS ahora FROM intento_login_fallido "
        f"WHERE {condicion} AND {_VENTANA} ORDER BY fecha, id_intento LIMIT 1 OFFSET %s",
        tuple(parametros) + (max(conteo - maximo, 0),),
    )
    fila = cursor.fetchone()
    fecha, ahora = _valor(fila, "fecha", 0), _valor(fila, "ahora", 1)
    if fecha is None or ahora is None:
        return VENTANA_MINUTOS * 60
    if isinstance(fecha, str):
        fecha = datetime.fromisoformat(fecha)
    if isinstance(ahora, str):
        ahora = datetime.fromisoformat(ahora)
    restante = (fecha + timedelta(minutes=VENTANA_MINUTOS) - ahora).total_seconds()
    return int(min(max(restante, 1), VENTANA_MINUTOS * 60))


def _comprobar_cupo(cursor, clave, ip):
    """Lanza LimiteAlcanzado si algún contador alcanzó su umbral."""
    par, cuenta, por_ip = _contar(cursor, clave, ip)
    esperas = []
    if ip is not None and par >= MAX_POR_PAR:
        esperas.append(_espera_hasta_cupo(
            cursor, "clave_cuenta = %s AND ip_cliente = %s", (clave, ip), par, MAX_POR_PAR))
    if cuenta >= MAX_POR_CUENTA:
        esperas.append(_espera_hasta_cupo(
            cursor, "clave_cuenta = %s", (clave,), cuenta, MAX_POR_CUENTA))
    if ip is not None and por_ip >= MAX_POR_IP:
        esperas.append(_espera_hasta_cupo(
            cursor, "ip_cliente = %s", (ip,), por_ip, MAX_POR_IP))
    if esperas:
        raise LimiteAlcanzado(max(esperas))


def verificar_cupo(cursor, clave, ip):
    """Prechequeo sin bloqueo ni escritura: rechaza barato a quien ya excedió
    un umbral. La garantía la da `reservar_intento`; esto solo ahorra bcrypt."""
    try:
        _comprobar_cupo(cursor, clave, ip)
    except mysql.connector.Error as error:
        raise _error_no_disponible(error)


# --- Reserva -----------------------------------------------------------------

def _adquirir_bloqueo(cursor, nombre, segundos):
    cursor.execute("SELECT GET_LOCK(%s, %s) AS bloqueo", (nombre, segundos))
    fila = cursor.fetchone()
    return _valor(fila, "bloqueo", 0) == 1


def _liberar_bloqueo(cursor, nombre):
    try:
        cursor.execute("SELECT RELEASE_LOCK(%s) AS liberado", (nombre,))
        cursor.fetchone()
    except Exception:
        # Si la conexión murió, MySQL ya liberó el bloqueo al cerrarla.
        logger.warning("Limitador de login: no se pudo liberar el bloqueo %s", nombre)


def _seccion_de_reserva(connection, cursor, clave, ip, id_usuario):
    tomado = False
    try:
        # Antes de esperar el bloqueo se termina la transacción de las lecturas
        # previas (usuario, prechequeo): bajo SERIALIZABLE esas lecturas toman
        # bloqueos de fila/rango, y quien está dentro de la sección podría
        # esperarlos mientras nosotros esperamos su bloqueo con nombre, una
        # espera cruzada que InnoDB no detecta.
        connection.rollback()
        if not _adquirir_bloqueo(cursor, NOMBRE_BLOQUEO_RESERVA, SEGUNDOS_ESPERA_BLOQUEO):
            logger.error("Limitador de login: no se obtuvo el bloqueo de reserva en %s s",
                         SEGUNDOS_ESPERA_BLOQUEO)
            raise LimitadorNoDisponible(segundos=SEGUNDOS_ESPERA_BLOQUEO)
        tomado = True
        # Termina la instantánea previa: el recuento debe ver todo lo que otras
        # secciones ya confirmaron (REPEATABLE READ fija la vista en la primera lectura).
        connection.rollback()
        _comprobar_cupo(cursor, clave, ip)
        cursor.execute(_SQL_INSERTAR, (clave, ip, id_usuario))
        id_intento = getattr(cursor, "lastrowid", None)
        connection.commit()
        return id_intento
    finally:
        if tomado:
            _liberar_bloqueo(cursor, NOMBRE_BLOQUEO_RESERVA)
        # Sin transacción abierta mientras se verifica la contraseña.
        _revertir(connection)


def reservar_intento(connection, cursor, clave, ip, id_usuario):
    """Reserva cupo para un intento y devuelve el id de la fila (o None si el
    cursor no lo informa). Lanza LimiteAlcanzado o LimitadorNoDisponible.

    Un deadlock (1213) o un timeout de bloqueo de fila (1205) reintenta la
    sección una vez; nada se había confirmado, así que no duplica la reserva.
    """
    for intento in range(2):
        try:
            return _seccion_de_reserva(connection, cursor, clave, ip, id_usuario)
        except mysql.connector.Error as error:
            if getattr(error, "errno", None) in (ERRNO_DEADLOCK, ERRNO_LOCK_WAIT_TIMEOUT) and intento == 0:
                logger.warning("Limitador de login: reintento tras errno %s", error.errno)
                continue
            raise _error_no_disponible(error)


def liberar_reserva(cursor, id_intento):
    """Borra la reserva propia tras un login exitoso. No confirma: va dentro de
    la transacción que registra el LOGIN. Un fallo se propaga (el login falla y
    la reserva queda, que es el lado seguro)."""
    if id_intento is not None:
        cursor.execute(_SQL_BORRAR_RESERVA, (id_intento,))


# --- Purga -------------------------------------------------------------------

def purgar_si_corresponde(connection, cursor, id_intento):
    """Cada CADA_N_RESERVAS_PURGAR reservas borra un lote de filas vencidas.

    Elegir por el id de la reserva hace la decisión determinista. Borra por
    clave primaria (sin bloqueos de rango sobre los índices que usa el login)
    y bajo un bloqueo con nombre propio para que solo un worker purgue a la vez.
    Cualquier error se registra como advertencia y no afecta al login.
    """
    if id_intento is None or id_intento % CADA_N_RESERVAS_PURGAR != 0:
        return
    tomado = False
    try:
        if not _adquirir_bloqueo(cursor, NOMBRE_BLOQUEO_PURGA, 0):
            return
        tomado = True
        cursor.execute(
            "SELECT id_intento FROM intento_login_fallido "
            f"WHERE fecha < DATE_SUB(UTC_TIMESTAMP(), INTERVAL {RETENCION_HORAS} HOUR) "
            "ORDER BY fecha, id_intento LIMIT %s",
            (LOTE_PURGA,),
        )
        ids = [_valor(fila, "id_intento", 0) for fila in cursor.fetchall()]
        if ids:
            marcadores = ", ".join(["%s"] * len(ids))
            cursor.execute(f"DELETE FROM intento_login_fallido WHERE id_intento IN ({marcadores})", tuple(ids))
        connection.commit()
    except Exception:
        logger.warning("Limitador de login: no se pudo purgar las filas vencidas")
        _revertir(connection)
    finally:
        if tomado:
            _liberar_bloqueo(cursor, NOMBRE_BLOQUEO_PURGA)
        _revertir(connection)


# --- Respuestas ----------------------------------------------------------------

def respuesta_limite(segundos):
    respuesta = jsonify({
        "error": MENSAJE_LIMITE,
        "codigo": CODIGO_LIMITE,
        "reintentar_en_segundos": segundos,
    })
    respuesta.status_code = 429
    respuesta.headers["Retry-After"] = str(segundos)
    return respuesta


def respuesta_no_disponible(segundos):
    respuesta = jsonify({
        "error": MENSAJE_NO_DISPONIBLE,
        "codigo": CODIGO_NO_DISPONIBLE,
    })
    respuesta.status_code = 503
    respuesta.headers["Retry-After"] = str(segundos)
    return respuesta
