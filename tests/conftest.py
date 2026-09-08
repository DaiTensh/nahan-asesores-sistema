from decimal import Decimal

import pytest
from flask import session as flask_session

from backend.app import app as flask_app
from backend.utils import auth as auth_utils


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

    Desde el arreglo de seguridad (a7e285c) el rol ya no se toma de la sesión:
    se relee de la base en cada solicitud. Sin este doble, el decorador abriría
    una conexión real con el MySQL del desarrollador, y entonces las pruebas
    dependerían de los datos sembrados y —peor— escribirían en esa base.

    La fila se arma con lo que la prueba declaró en la sesión, de modo que
    `iniciar_sesion(usuario_id=2, rol_id=2)` sigue significando exactamente lo
    que significaba antes: «hay un usuario jurídico autenticado».
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
            "nombre_rol": auth_utils.ROLES.get(id_rol, auth_utils.ROL_ADMINISTRADOR),
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

    Va como autouse a propósito: si dependiera de que cada prueba se acuerde de
    pedirla, la que se olvide vuelve a escribir en la base del desarrollador sin
    que nadie lo note.
    """
    monkeypatch.setattr(auth_utils, "get_connection", lambda: AuthConnection())


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
def iniciar_sesion(client):
    def login(
        usuario_id=1,
        rol_id=1,
        area_id=3,
        nombre="Usuario Prueba",
    ):
        with client.session_transaction() as session:
            session["usuario_id"] = usuario_id
            session["rol_id"] = rol_id
            session["area_id"] = area_id
            session["nombre"] = nombre

    return login


@pytest.fixture
def decimal_values():
    return {
        "ninety_minutes": Decimal("90.00"),
        "hourly_rate": Decimal("30000.00"),
        "amount": Decimal("45000.00"),
    }
