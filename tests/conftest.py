from decimal import Decimal

import pytest

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
