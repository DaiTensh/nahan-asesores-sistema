import sqlite3

import pytest

import backend.routes.auth_routes as auth_routes
import backend.routes.clientes_routes as clientes_routes
import backend.utils.auth as auth_utils
from backend.utils.clientes_recientes import PARAMETRO_CLIENTES_RECIENTES


class SQLiteCursor:
    def __init__(self, connection, dictionary):
        self.cursor = connection.cursor()
        self.dictionary = dictionary
        self.rowcount = 0
        self.lastrowid = None

    def execute(self, sql, params=()):
        sql = sql.replace("CURRENT_TIMESTAMP(6)", "rf47_now()")
        sql = sql.replace(
            "ON DUPLICATE KEY UPDATE fecha_interaccion = rf47_now()",
            "ON CONFLICT(id_usuario, id_cliente) DO UPDATE SET fecha_interaccion = rf47_now()",
        )
        self.cursor.execute(sql.replace("%s", "?"), tuple(params))
        self.rowcount = self.cursor.rowcount
        self.lastrowid = self.cursor.lastrowid

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row is not None and self.dictionary else row

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [dict(row) for row in rows] if self.dictionary else rows

    def close(self):
        self.cursor.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


class SQLiteConnection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self, dictionary=False):
        return SQLiteCursor(self.connection, dictionary)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        pass


@pytest.fixture
def rf47_client(client, iniciar_sesion, monkeypatch):
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    ticks = [0]

    def fecha_actual():
        ticks[0] += 1
        return f"2026-11-01 12:00:00.{ticks[0]:06d}"

    database.create_function("rf47_now", 0, fecha_actual)
    database.executescript(
        """
        CREATE TABLE usuario (id_usuario INTEGER PRIMARY KEY);
        CREATE TABLE cliente (
            id_cliente INTEGER PRIMARY KEY,
            rut TEXT NOT NULL,
            razon_social TEXT NOT NULL,
            email TEXT,
            telefono TEXT,
            direccion TEXT,
            estado TEXT NOT NULL
        );
        CREATE TABLE cliente_area (id_cliente INTEGER, id_area INTEGER);
        CREATE TABLE cliente_reciente (
            id_usuario INTEGER NOT NULL,
            id_cliente INTEGER NOT NULL,
            fecha_interaccion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id_usuario, id_cliente),
            FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario) ON DELETE CASCADE,
            FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente) ON DELETE CASCADE
        );
        CREATE TABLE parametros_sistema (
            nombre_parametro TEXT PRIMARY KEY,
            valor_parametro TEXT NOT NULL,
            tipo_dato TEXT NOT NULL,
            descripcion TEXT
        );
        CREATE TABLE auditoria (
            id_auditoria INTEGER PRIMARY KEY,
            id_usuario INTEGER,
            tabla_afectada TEXT,
            id_registro INTEGER,
            accion TEXT,
            datos_anteriores TEXT,
            datos_nuevos TEXT
        );
        INSERT INTO usuario VALUES (1), (2);
        INSERT INTO cliente VALUES
          (1, '11-1', 'Cliente Uno', NULL, NULL, NULL, 'ACTIVO'),
          (2, '22-2', 'Cliente Dos', NULL, NULL, NULL, 'ACTIVO'),
                    (3, '33-3', 'Cliente Inactivo', NULL, NULL, NULL, 'INACTIVO'),
                    (4, '44-4', 'Cliente Cuatro', NULL, NULL, NULL, 'ACTIVO'),
                    (5, '55-5', 'Cliente Cinco', NULL, NULL, NULL, 'ACTIVO'),
                    (6, '66-6', 'Cliente Seis', NULL, NULL, NULL, 'ACTIVO'),
                    (7, '77-7', 'Cliente Siete', NULL, NULL, NULL, 'ACTIVO');
        INSERT INTO parametros_sistema VALUES
          ('CLIENTES_RECIENTES_LIMITE', '5', 'INT', 'Máximo global');
        """
    )

    def connection_factory():
        return SQLiteConnection(database)

    monkeypatch.setattr(clientes_routes, "get_connection", connection_factory)
    monkeypatch.setattr(auth_routes, "get_connection", connection_factory)
    iniciar_sesion(usuario_id=1, rol_id=1)
    yield client, database
    database.close()


def test_rf47_t01_t05_registra_visitas_y_ordena_por_recencia(rf47_client):
    client, database = rf47_client
    assert database.execute(
        "SELECT valor_parametro FROM parametros_sistema WHERE nombre_parametro = ?",
        (PARAMETRO_CLIENTES_RECIENTES,),
    ).fetchone()[0] == "5"

    assert client.get("/api/clientes/1").status_code == 200
    database.execute(
        "UPDATE cliente_reciente SET fecha_interaccion = '2000-01-01 00:00:00' WHERE id_cliente = 1"
    )
    database.commit()
    assert client.get("/api/clientes/2").status_code == 200
    assert client.get("/api/clientes/1").status_code == 200

    respuesta = client.get("/api/clientes/recientes")
    assert respuesta.status_code == 200
    assert [fila["id_cliente"] for fila in respuesta.get_json()["clientes_recientes"]] == [1, 2]
    assert database.execute("SELECT COUNT(*) FROM cliente_reciente WHERE id_usuario = 1 AND id_cliente = 1").fetchone()[0] == 1


def test_rf47_t02_limite_predeterminado_devuelve_hasta_cinco(rf47_client):
    client, _ = rf47_client
    for id_cliente in (1, 2, 4, 5, 6, 7):
        assert client.get(f"/api/clientes/{id_cliente}").status_code == 200

    respuesta = client.get("/api/clientes/recientes")
    assert respuesta.status_code == 200
    assert respuesta.get_json()["limite"] == 5
    assert [fila["id_cliente"] for fila in respuesta.get_json()["clientes_recientes"]] == [7, 6, 5, 4, 2]


@pytest.mark.parametrize("limite", [1, 20])
def test_rf47_t03_actualiza_limite_administrativo_valido(rf47_client, limite):
    client, _ = rf47_client
    for id_cliente in (1, 2, 4, 5, 6, 7):
        assert client.get(f"/api/clientes/{id_cliente}").status_code == 200

    respuesta = client.put("/api/parametros/clientes-recientes", json={"limite": limite})
    assert respuesta.status_code == 200
    assert respuesta.get_json()["limite"] == limite
    recientes = client.get("/api/clientes/recientes").get_json()["clientes_recientes"]
    assert len(recientes) == min(limite, 6)


@pytest.mark.parametrize("limite", [0, 21, "1.5", True, None])
def test_rf47_t04_rechaza_limites_invalidos_sin_error_500(rf47_client, limite):
    client, _ = rf47_client
    respuesta = client.put("/api/parametros/clientes-recientes", json={"limite": limite})
    assert respuesta.status_code == 400


def test_rf47_t06_historial_aislado_e_id_usuario_enviado_ignorado(rf47_client, iniciar_sesion):
    client, _ = rf47_client
    assert client.get("/api/clientes/1").status_code == 200
    iniciar_sesion(usuario_id=2, rol_id=2)
    respuesta = client.get("/api/clientes/recientes?id_usuario=1")
    assert respuesta.status_code == 200
    assert respuesta.get_json()["clientes_recientes"] == []


def test_rf47_t07_excluye_clientes_inactivos(rf47_client):
    client, database = rf47_client
    assert client.get("/api/clientes/3").status_code == 200
    assert database.execute("SELECT COUNT(*) FROM cliente_reciente").fetchone()[0] == 0
    database.execute(
        "INSERT INTO cliente_reciente (id_usuario, id_cliente) VALUES (1, 3)"
    )
    database.commit()
    respuesta = client.get("/api/clientes/recientes")
    assert respuesta.status_code == 200
    assert respuesta.get_json()["clientes_recientes"] == []


def test_rf47_t08_usuario_sin_rol_operativo_no_consulta_recientes(rf47_client, monkeypatch, iniciar_sesion):
    client, _ = rf47_client
    monkeypatch.setitem(auth_utils.ROLES, 4, "ROL_NO_OPERATIVO")
    iniciar_sesion(usuario_id=1, rol_id=4)
    assert client.get("/api/clientes/recientes").status_code == 403


def test_rf47_consulta_de_ficha_no_autorizada_no_registra_interaccion(rf47_client, monkeypatch, iniciar_sesion):
    client, database = rf47_client
    monkeypatch.setitem(auth_utils.ROLES, 4, "ROL_NO_OPERATIVO")
    iniciar_sesion(usuario_id=1, rol_id=4)
    assert client.get("/api/clientes/1").status_code == 403
    assert database.execute("SELECT COUNT(*) FROM cliente_reciente").fetchone()[0] == 0


def test_rf47_t09_eliminacion_definitiva_limpia_referencias(rf47_client):
    client, database = rf47_client
    assert client.get("/api/clientes/1").status_code == 200
    respuesta = client.delete("/api/clientes/1/eliminar-definitivo")
    assert respuesta.status_code == 200
    assert database.execute("SELECT COUNT(*) FROM cliente_reciente WHERE id_cliente = 1").fetchone()[0] == 0


def test_rf47_t10_ficha_inexistente_no_registra_interaccion(rf47_client):
    client, database = rf47_client
    assert client.get("/api/clientes/999").status_code == 404
    assert database.execute("SELECT COUNT(*) FROM cliente_reciente").fetchone()[0] == 0