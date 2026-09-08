from decimal import Decimal

import pytest
from flask import session as flask_session

from backend.app import app as flask_app
from backend.utils import auth as auth_module


class FakeCursor:
    def __init__(self, handler, dictionary=False):
        self.handler = handler
        self.dictionary = dictionary
        self.executed = []
        self.results = []
        self.rowcount = 1
        self.lastrowid = None

    def execute(self, sql, params=None):
        params = params or ()
        self.executed.append((sql, params))
        self.results = self.handler(sql, params, self) or []

    def fetchone(self):
        if not self.results:
            return None
        return self.results.pop(0)

    def fetchall(self):
        results = self.results
        self.results = []
        return results

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


class FakeConnection:
    def __init__(self, handler):
        self.handler = handler
        self.cursors = []
        self.commits = 0
        self.rollbacks = 0
        self.transactions = 0
        self.closed = False

    def cursor(self, dictionary=False):
        cursor = FakeCursor(self.handler, dictionary=dictionary)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def start_transaction(self):
        self.transactions += 1

    def close(self):
        self.closed = True

    @property
    def executed(self):
        return [
            statement
            for cursor in self.cursors
            for statement in cursor.executed
        ]


def normalize_sql(sql):
    return " ".join(sql.split())


class AuthCursor:
    """Responde la única consulta que hace `obtener_usuario_actual()`.

    Es la red de seguridad de la fixture `iniciar_sesion`: esa cubre a las
    pruebas que la piden, pero una prueba que escribe la sesión a mano —
    `test_auth_me_autenticado`, por ejemplo— seguiría abriendo una conexión
    real contra el MySQL del desarrollador. Esto va como autouse justamente
    para que no dependa de que cada prueba se acuerde: la que se olvide
    volvería a leer, y a escribir, en una base que no es de pruebas.

    La fila se arma con lo que haya en la sesión, de modo que el significado
    de la prueba no cambia.
    """

    def __init__(self):
        self.fila = None

    def execute(self, sql, params=None):
        usuario_id = (params or (flask_session.get("usuario_id"),))[0]
        if not usuario_id:
            self.fila = None
            return
        id_rol = flask_session.get("rol_id", 1)
        self.fila = {
            "id_usuario": usuario_id,
            "nombres": flask_session.get("nombre", "Usuario Prueba"),
            "estado": flask_session.get("estado", "ACTIVO"),
            "id_rol": id_rol,
            "nombre_rol": auth_module.ROLES.get(id_rol, auth_module.ROL_ADMINISTRADOR),
            "id_area": flask_session.get("area_id", 3),
        }

    def fetchone(self):
        return self.fila

    def close(self):
        pass


class AuthConnection:
    def cursor(self, dictionary=False):
        return AuthCursor()

    def close(self):
        pass


@pytest.fixture(autouse=True)
def autenticacion_aislada(monkeypatch):
    """Ninguna prueba debe alcanzar el MySQL real a través del decorador.

    `iniciar_sesion` vuelve a parchear lo mismo con una fila más precisa; como
    ambas usan monkeypatch, la última gana y las dos se deshacen al terminar.
    """
    monkeypatch.setattr(auth_module, "get_connection", lambda: AuthConnection())


@pytest.fixture
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


@pytest.fixture
def fake_connection_factory():
    def build(handler):
        return FakeConnection(handler)

    return build


@pytest.fixture
def iniciar_sesion(client, monkeypatch):
    """Simula un usuario autenticado sin depender de los datos reales
    sembrados en la base de datos.

    `obtener_usuario_actual()` (backend/utils/auth.py) resuelve el usuario
    consultando la BD en cada solicitud —a propósito, es la corrección de
    seguridad de REV-001 (un cambio de rol o una desactivación deben surtir
    efecto de inmediato)—, así que basta con escribir el `usuario_id` en la
    sesión: el rol y el estado ya no se leen de ahí. Para que los tests sigan
    pudiendo simular "usuario con tal rol" sin importar qué haya sembrado
    `database/seed_dev.py` en ese momento, esta fixture además reemplaza la
    conexión que usa `obtener_usuario_actual()` por una fila controlada que
    coincide con los parámetros recibidos.
    """
    def login(
        usuario_id=1,
        rol_id=1,
        area_id=3,
        nombre="Usuario Prueba",
        estado="ACTIVO",
    ):
        with client.session_transaction() as session:
            session["usuario_id"] = usuario_id
            session["rol_id"] = rol_id
            session["area_id"] = area_id
            session["nombre"] = nombre

        fila_usuario = {
            "id_usuario": usuario_id,
            "nombres": nombre,
            "estado": estado,
            "id_rol": rol_id,
            "nombre_rol": auth_module.ROLES.get(rol_id),
            "id_area": area_id,
        }

        def handler(sql, params, cursor):
            return [fila_usuario.copy()]

        connection = FakeConnection(handler)
        monkeypatch.setattr(auth_module, "get_connection", lambda: connection)

    return login


@pytest.fixture
def decimal_values():
    return {
        "ninety_minutes": Decimal("90.00"),
        "hourly_rate": Decimal("30000.00"),
        "amount": Decimal("45000.00"),
    }
