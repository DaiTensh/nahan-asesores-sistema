"""Dobles de prueba para el limitador de login (SEC-02).

El limitador usa SQL de MySQL que SQLite no entiende (GET_LOCK, RELEASE_LOCK,
UTC_TIMESTAMP, DATE_SUB, WEIGHT_STRING). Muchas suites hacen un login real
sobre una base SQLite en memoria; en lugar de apagar el limitador, estas
clases enseñan a SQLite lo justo para que el limitador real corra contra una
tabla `intento_login_fallido` real:

* ConexionSQLite: toda conexión `sqlite3.connect()` creada durante una prueba
  trae la tabla, anota las sentencias que ejecuta (bitácora, con COMMIT y
  ROLLBACK), simula los bloqueos con nombre y admite inyectar errores de MySQL.
* respuesta_por_defecto: lo mismo, pero para los dobles sin base de datos
  (FakeCursor): cupo siempre libre, bloqueos concedidos.

Qué NO reproduce: la competencia entre solicitudes ni el aislamiento de
InnoDB (se prueban contra MySQL real) ni el collation: el peso del correo se
emula con una normalización aproximada; que MySQL produce la misma clave que
su comparación `=` se comprobó contra MySQL real.
"""
import re
import sqlite3
import unicodedata

ESQUEMA_LIMITADOR = """
CREATE TABLE IF NOT EXISTS intento_login_fallido (
    id_intento INTEGER PRIMARY KEY AUTOINCREMENT,
    clave_cuenta BLOB NOT NULL,
    ip_cliente BLOB,
    id_usuario INTEGER,
    fecha TEXT NOT NULL
);
"""

_PESO = re.compile(
    r"HEX\(WEIGHT_STRING\(CAST\(\? AS CHAR CHARACTER SET utf8mb4\) COLLATE utf8mb4_unicode_ci\)\)"
)
_DATE_SUB = re.compile(r"DATE_SUB\(UTC_TIMESTAMP\(\), INTERVAL (\d+) (MINUTE|HOUR)\)")


def peso_correo(texto):
    """Emula HEX(WEIGHT_STRING(... utf8mb4_unicode_ci)): mayúsculas, acentos y
    caracteres ignorables no cuentan; los espacios finales dejan unidades 0209."""
    texto = unicodedata.normalize("NFKD", texto.casefold())
    relleno = len(texto) - len(texto.rstrip(" "))
    limpio = "".join(
        c for c in texto.rstrip(" ")
        if unicodedata.category(c) not in ("Mn", "Cf", "Cc")
    )
    unidades = "".join(f"{(ord(c) if ord(c) <= 0xFFFF else 0xFFFD):04X}" for c in limpio)
    return unidades + "0209" * relleno


def _sentencia(sql):
    return " ".join(sql.split())


def _es_del_limitador(sql):
    return any(clave in sql for clave in ("intento_login_fallido", "GET_LOCK(", "RELEASE_LOCK(", "WEIGHT_STRING("))


class CursorSQLite(sqlite3.Cursor):
    def execute(self, sql, params=()):
        conexion = self.connection
        conexion.bitacora.append(_sentencia(sql))
        conexion._provocar_fallo(_sentencia(sql))
        sql, params = _adaptar(conexion, sql, tuple(params))
        return super().execute(sql, params)


class ConexionSQLite(sqlite3.Connection):
    """Conexión SQLite con la tabla del limitador y funciones de MySQL emuladas."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bitacora = []      # sentencias SQL, más "COMMIT" y "ROLLBACK", en orden
        self.bloqueos = {}      # nombre -> "propio" | "ajeno" (un test puede poner "ajeno")
        self.fallos = []        # [[patrón, función_que_crea_la_excepción, veces]]
        self.create_function("NH_PESO", 1, peso_correo, deterministic=True)
        self.executescript(ESQUEMA_LIMITADOR)

    def cursor(self, factory=None):
        return super().cursor(CursorSQLite)

    def commit(self):
        self.bitacora.append("COMMIT")
        super().commit()

    def rollback(self):
        self.bitacora.append("ROLLBACK")
        super().rollback()

    def inyectar_fallo(self, patron, crear_excepcion, veces=1):
        """La próxima(s) `veces` sentencias que contengan `patron` lanzan la excepción."""
        self.fallos.append([patron, crear_excepcion, veces])

    def _provocar_fallo(self, sentencia):
        for entrada in self.fallos:
            patron, crear_excepcion, veces = entrada
            if veces > 0 and patron in sentencia:
                entrada[2] -= 1
                raise crear_excepcion()


def _adaptar(conexion, sql, params):
    if "GET_LOCK(" in sql:
        nombre = params[0]
        concedido = conexion.bloqueos.get(nombre) != "ajeno"
        if concedido:
            conexion.bloqueos[nombre] = "propio"
        return "SELECT ? AS bloqueo", (1 if concedido else 0,)
    if "RELEASE_LOCK(" in sql:
        nombre = params[0]
        liberado = conexion.bloqueos.get(nombre) == "propio"
        if liberado:
            del conexion.bloqueos[nombre]
        return "SELECT ? AS liberado", (1 if liberado else None,)
    if "intento_login_fallido" in sql or "WEIGHT_STRING(" in sql:
        sql = _PESO.sub("NH_PESO(?)", sql)
        sql = _DATE_SUB.sub(
            lambda m: f"datetime('now', '-{m.group(1)} {'minutes' if m.group(2) == 'MINUTE' else 'hours'}')",
            sql,
        )
        sql = sql.replace("UTC_TIMESTAMP()", "datetime('now')")
    return sql, params


def respuesta_por_defecto(sql, params):
    """Respuesta de un doble sin base de datos a una sentencia del limitador:
    cupo libre y bloqueos concedidos. None si la sentencia no es del limitador."""
    sentencia = _sentencia(sql)
    if not _es_del_limitador(sentencia):
        return None
    if "WEIGHT_STRING(" in sentencia:
        return [{"peso": peso_correo(params[0])}]
    if "GET_LOCK(" in sentencia:
        return [{"bloqueo": 1}]
    if "RELEASE_LOCK(" in sentencia:
        return [{"liberado": 1}]
    if "SELECT (SELECT COUNT(*)" in sentencia:
        return [{"par": 0, "cuenta": 0, "por_ip": 0}]
    return []


def instalar(monkeypatch):
    """Hace que todo `sqlite3.connect()` de la prueba devuelva ConexionSQLite."""
    original = sqlite3.connect

    def conectar(*args, **kwargs):
        if len(args) < 6:
            kwargs.setdefault("factory", ConexionSQLite)
        return original(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", conectar)
