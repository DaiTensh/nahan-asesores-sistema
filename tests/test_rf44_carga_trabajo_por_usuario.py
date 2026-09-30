import pytest

import backend.routes.reportes_routes as reportes_routes
from backend.app import app as flask_app


@pytest.fixture
def cliente_admin(client, iniciar_sesion):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3, nombre="Admin RF44")
    return client


@pytest.fixture
def cliente_no_admin(client, iniciar_sesion):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1, nombre="Usuario RF44")
    return client


def _fake_connection(handler):
    class FakeCursor:
        def __init__(self, dictionary=False):
            self._dictionary = dictionary
            self._rows = []
            self._executed = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.close()

        def execute(self, sql, params=()):
            self._executed.append((sql, params))
            self._rows = handler(sql, params, self) or []

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            rows = list(self._rows)
            self._rows = []
            return rows

        def close(self):
            pass

    class FakeConnection:
        def cursor(self, dictionary=False):
            return FakeCursor(dictionary=dictionary)

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    return FakeConnection()


def test_admin_consulta_carga_por_usuario_con_desglose_por_estado(monkeypatch, cliente_admin):
    def handler(sql, params, cursor):
        if "FROM usuario u" in sql and "WHERE u.estado = 'ACTIVO'" in sql:
            return [
                {"id_usuario": 2, "nombres": "Ana", "id_area": 1, "nombre_area": "Jurídica", "estado": "ACTIVO"},
                {"id_usuario": 3, "nombres": "Beto", "id_area": 1, "nombre_area": "Jurídica", "estado": "ACTIVO"},
                {"id_usuario": 4, "nombres": "Carla", "id_area": 2, "nombre_area": "Contable", "estado": "ACTIVO"},
                {"id_usuario": 5, "nombres": "Diego", "id_area": 1, "nombre_area": "Jurídica", "estado": "INACTIVO"},
            ]
        if "LEFT JOIN tarea t" in sql:
            return [
                {"id_usuario": 2, "PENDIENTE": 1, "EN_PROCESO": 1, "EN_REVISION": 0, "COMPLETADA": 0, "CANCELADA": 0},
                {"id_usuario": 3, "PENDIENTE": 0, "EN_PROCESO": 0, "EN_REVISION": 1, "COMPLETADA": 1, "CANCELADA": 0},
                {"id_usuario": 4, "PENDIENTE": 0, "EN_PROCESO": 0, "EN_REVISION": 0, "COMPLETADA": 0, "CANCELADA": 0},
            ]
        return []

    monkeypatch.setattr(reportes_routes, "get_connection", lambda: _fake_connection(handler))

    response = cliente_admin.get("/api/reportes/carga-por-usuario")
    data = response.get_json()

    assert response.status_code == 200
    assert data["usuarios"][0]["usuario"] == "Ana"
    assert data["usuarios"][0]["total_tareas"] == 2
    assert data["usuarios"][0]["por_estado"]["PENDIENTE"] == 1
    assert data["usuarios"][0]["por_estado"]["EN_PROCESO"] == 1
    assert data["usuarios"][0]["por_estado"]["EN_REVISION"] == 0
    assert data["usuarios"][1]["por_estado"]["COMPLETADA"] == 1
    assert data["usuarios"][2]["por_estado"]["PENDIENTE"] == 0
    assert data["usuarios"][2]["total_tareas"] == 0


def test_admin_puede_filtrar_por_area_y_ignora_inactivos(monkeypatch, cliente_admin):
    def handler(sql, params, cursor):
        if "WHERE u.estado = 'ACTIVO'" in sql and "u.id_area = %s" in sql:
            return [
                {"id_usuario": 2, "nombres": "Ana", "id_area": 1, "nombre_area": "Jurídica", "estado": "ACTIVO"},
                {"id_usuario": 5, "nombres": "Diego", "id_area": 1, "nombre_area": "Jurídica", "estado": "INACTIVO"},
            ]
        if "LEFT JOIN tarea t" in sql:
            return [
                {"id_usuario": 2, "PENDIENTE": 2, "EN_PROCESO": 1, "EN_REVISION": 0, "COMPLETADA": 0, "CANCELADA": 1},
            ]
        return []

    monkeypatch.setattr(reportes_routes, "get_connection", lambda: _fake_connection(handler))

    response = cliente_admin.get("/api/reportes/carga-por-usuario?id_area=1")
    data = response.get_json()

    assert response.status_code == 200
    assert len(data["usuarios"]) == 1
    assert data["usuarios"][0]["usuario"] == "Ana"
    assert data["usuarios"][0]["id_area"] == 1
    assert data["usuarios"][0]["total_tareas"] == 4
    assert data["usuarios"][0]["por_estado"]["CANCELADA"] == 1


def test_usuario_no_admin_no_tiene_acceso_global(monkeypatch, cliente_no_admin):
    response = cliente_no_admin.get("/api/reportes/carga-por-usuario")
    assert response.status_code == 403


def test_no_hay_usuarios_activos_devuelve_respuesta_vacia_controlada(monkeypatch, cliente_admin):
    def handler(sql, params, cursor):
        if "FROM usuario u" in sql and "WHERE u.estado = 'ACTIVO'" in sql:
            return []
        return []

    monkeypatch.setattr(reportes_routes, "get_connection", lambda: _fake_connection(handler))

    response = cliente_admin.get("/api/reportes/carga-por-usuario")
    data = response.get_json()

    assert response.status_code == 200
    assert data["usuarios"] == []
    assert data["mensaje"] == "No hay usuarios activos para los criterios seleccionados"


def test_totales_coinciden_con_el_desglose_por_estado(monkeypatch, cliente_admin):
    def handler(sql, params, cursor):
        if "FROM usuario u" in sql and "WHERE u.estado = 'ACTIVO'" in sql:
            return [
                {"id_usuario": 2, "nombres": "Ana", "id_area": 1, "nombre_area": "Jurídica", "estado": "ACTIVO"},
                {"id_usuario": 3, "nombres": "Beto", "id_area": 1, "nombre_area": "Jurídica", "estado": "ACTIVO"},
            ]
        if "LEFT JOIN tarea t" in sql:
            return [
                {"id_usuario": 2, "PENDIENTE": 1, "EN_PROCESO": 1, "EN_REVISION": 1, "COMPLETADA": 1, "CANCELADA": 1},
                {"id_usuario": 3, "PENDIENTE": 0, "EN_PROCESO": 0, "EN_REVISION": 0, "COMPLETADA": 0, "CANCELADA": 0},
            ]
        return []

    monkeypatch.setattr(reportes_routes, "get_connection", lambda: _fake_connection(handler))

    response = cliente_admin.get("/api/reportes/carga-por-usuario")
    data = response.get_json()

    assert response.status_code == 200
    total_ana = sum(data["usuarios"][0]["por_estado"].values())
    assert total_ana == data["usuarios"][0]["total_tareas"] == 5
