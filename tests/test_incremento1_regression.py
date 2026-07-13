from decimal import Decimal
from pathlib import Path

import pytest

from backend.app import create_app
from backend.routes import auth_routes
from backend.routes import clientes_routes
from backend.routes import control_horas_routes
from backend.routes import tareas_routes
from backend.routes import usuarios_routes
from tests.conftest import normalize_sql


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_login_con_credenciales_validas(client, fake_connection_factory, monkeypatch):
    usuario_db = {
        "id_usuario": 1,
        "nombres": "Usuario Prueba",
        "email": "usuario.prueba@nahan.test",
        "password_hash": "hash-controlado",
        "estado": "ACTIVO",
        "id_rol": 1,
        "nombre_rol": "ADMINISTRADOR",
        "id_area": 3,
        "nombre_area": "ADMINISTRACION",
    }

    def handler(sql, params, cursor):
        if "FROM usuario u" in normalize_sql(sql):
            return [usuario_db.copy()]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(auth_routes, "get_connection", lambda: connection)
    monkeypatch.setattr(auth_routes, "check_password", lambda password, password_hash: True)

    response = client.post(
        "/api/login",
        json={
            "email": "usuario.prueba@nahan.test",
            "password": "clave-correcta",
        },
    )

    data = response.get_json()

    assert response.status_code == 200
    assert data["message"] == "Inicio de sesión correcto"
    assert data["usuario"]["email"] == "usuario.prueba@nahan.test"
    assert "password_hash" not in data["usuario"]
    with client.session_transaction() as session:
        assert session["usuario_id"] == 1
        assert session["rol_id"] == 1
        assert session["area_id"] == 3
        assert session["nombre"] == "Usuario Prueba"
    assert connection.closed is True


def test_app_importable_para_gunicorn():
    from backend.app import app

    assert app.name == "backend.app"
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True


def test_app_produccion_sin_secret_key_falla(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_app_configura_cookies_y_cors_desde_entorno(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "clave-test-produccion")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("SESSION_COOKIE_HTTPONLY", "true")
    monkeypatch.setenv("SESSION_COOKIE_SAMESITE", "Lax")
    monkeypatch.setenv("PERMANENT_SESSION_LIFETIME", "120")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://127.0.0.1:5500")
    monkeypatch.setenv("APP_TIMEZONE", "America/Santiago")

    app = create_app()

    assert app.config["DEBUG"] is False
    assert app.config["SECRET_KEY"] == "clave-test-produccion"
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() == 7200
    assert app.config["APP_TIMEZONE"] == "America/Santiago"


def test_login_con_credenciales_invalidas(client, fake_connection_factory, monkeypatch):
    def handler(sql, params, cursor):
        if "FROM usuario u" in normalize_sql(sql):
            return []
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(auth_routes, "get_connection", lambda: connection)

    response = client.post(
        "/api/login",
        json={
            "email": "nadie@nahan.test",
            "password": "clave-incorrecta",
        },
    )

    data = response.get_json()

    assert response.status_code == 401
    assert data == {"error": "Credenciales incorrectas"}
    with client.session_transaction() as session:
        assert "usuario_id" not in session
    assert connection.closed is True


def test_auth_me_autenticado(client):
    with client.session_transaction() as session:
        session["usuario_id"] = 1
        session["rol_id"] = 1
        session["area_id"] = 3
        session["nombre"] = "Usuario Prueba"

    response = client.get("/api/auth/me")
    data = response.get_json()

    assert response.status_code == 200
    assert data["usuario"] == {
        "id_usuario": 1,
        "nombres": "Usuario Prueba",
        "id_rol": 1,
        "nombre_rol": "ADMINISTRADOR",
        "id_area": 3,
    }
    assert data["permisos"] == {"es_admin": True}


def test_auth_me_sin_sesion(client):
    response = client.get("/api/auth/me")
    data = response.get_json()

    assert response.status_code == 401
    assert data == {"error": "No autenticado"}


def test_logout_destruye_sesion(client):
    with client.session_transaction() as session:
        session["usuario_id"] = 1
        session["rol_id"] = 1
        session["area_id"] = 3
        session["nombre"] = "Usuario Prueba"

    response = client.post("/api/logout")
    data = response.get_json()

    assert response.status_code == 200
    assert data == {"message": "Sesión cerrada correctamente"}

    with client.session_transaction() as session:
        assert "usuario_id" not in session
        assert "rol_id" not in session
        assert "area_id" not in session
        assert "nombre" not in session


def test_listado_de_clientes(client, fake_connection_factory, monkeypatch, iniciar_sesion):
    iniciar_sesion()
    clientes = [
        {
            "id_cliente": 10,
            "rut": "11.111.111-1",
            "razon_social": "Cliente Uno SpA",
            "estado": "ACTIVO",
            "telefono": "111111111",
        },
        {
            "id_cliente": 20,
            "rut": "22.222.222-2",
            "razon_social": "Cliente Dos Ltda",
            "estado": "INACTIVO",
            "telefono": None,
        },
    ]

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT DISTINCT c.id_cliente" in normalized:
            return [cliente.copy() for cliente in clientes]
        if "SELECT a.nombre_area FROM cliente_area" in normalized:
            id_cliente = params[0]
            if id_cliente == 10:
                return [{"nombre_area": "JURIDICA"}]
            return [{"nombre_area": "CONTABLE"}]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: connection)

    response = client.get("/api/clientes/listado?pagina=1&limite=7")
    data = response.get_json()

    assert response.status_code == 200
    assert data["clientes"][0]["razon_social"] == "Cliente Uno SpA"
    assert data["clientes"][0]["areas_nombres"] == "JURIDICA"
    assert data["clientes"][1]["areas_nombres"] == "CONTABLE"


def test_registro_de_cliente(client, fake_connection_factory, monkeypatch, iniciar_sesion):
    iniciar_sesion()
    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT id_cliente FROM cliente WHERE rut" in normalized:
            return []
        if "INSERT INTO cliente" in normalized:
            cursor.lastrowid = 123
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: connection)

    response = client.post(
        "/api/clientes",
        json={
            "rut": "33.333.333-3",
            "razon_social": "Cliente Nuevo SpA",
            "email": "cliente.nuevo@nahan.test",
            "telefono": "333333333",
            "direccion": "Direccion de prueba 123",
            "areas": [1, 2],
        },
    )
    data = response.get_json()

    assert response.status_code == 201
    assert data == {
        "message": "Cliente incorporado exitosamente junto a sus áreas asociadas."
    }
    assert connection.commits == 1
    assert any("INSERT INTO cliente_area" in normalize_sql(sql) for sql, _ in connection.executed)


def test_modificacion_de_cliente(client, fake_connection_factory, monkeypatch, iniciar_sesion):
    iniciar_sesion()
    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT id_cliente FROM cliente WHERE id_cliente" in normalized:
            return [(10,)]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: connection)

    response = client.put(
        "/api/clientes/10",
        json={
            "razon_social": "Cliente Modificado SpA",
            "email": "modificado@nahan.test",
            "telefono": "999999999",
            "direccion": "Nueva direccion",
            "areas": [1],
        },
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data == {"message": "Expediente modificado con éxito."}
    assert connection.commits == 1
    assert any("UPDATE cliente SET" in normalize_sql(sql) for sql, _ in connection.executed)
    assert any("DELETE FROM cliente_area" in normalize_sql(sql) for sql, _ in connection.executed)


def test_creacion_de_tarea(client, fake_connection_factory, monkeypatch, iniciar_sesion):
    iniciar_sesion(usuario_id=1, rol_id=1)

    def handler(sql, params, cursor):
        if "SELECT id_usuario, estado FROM usuario" in normalize_sql(sql):
            return [(2, "ACTIVO")]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    response = client.post(
        "/api/tareas",
        json={
            "id_cliente": 10,
            "areas": [1, 2],
            "id_responsable": 2,
            "id_creador": 1,
            "titulo": "Tarea de prueba",
            "descripcion": "Descripcion congelada para regresion",
            "prioridad": "MEDIA",
            "fecha_vencimiento": "2026-08-01",
        },
    )
    data = response.get_json()

    inserts = [
        sql for sql, _ in connection.executed
        if "INSERT INTO tarea" in normalize_sql(sql)
    ]

    assert response.status_code == 201
    assert data == {"message": "Tareas creadas correctamente"}
    assert len(inserts) == 2
    assert connection.commits == 1


def test_actualizacion_de_estado_de_tarea(client, fake_connection_factory, monkeypatch, iniciar_sesion):
    iniciar_sesion()
    def handler(sql, params, cursor):
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    response = client.put(
        "/api/tareas/50/estado",
        json={"estado": "EN_PROCESO"},
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data == {"message": "Estado actualizado correctamente"}
    assert connection.commits == 1
    assert any("UPDATE tarea SET estado" in normalize_sql(sql) for sql, _ in connection.executed)


def test_listado_de_usuarios(client, fake_connection_factory, monkeypatch, iniciar_sesion):
    iniciar_sesion()
    usuarios = [
        {
            "id_usuario": 1,
            "id_rol": 1,
            "id_area": 3,
            "nombres": "Admin Prueba",
            "email": "admin@nahan.test",
            "estado": "ACTIVO",
            "fecha_creacion": "2026-01-01 10:00:00",
            "nombre_rol": "ADMINISTRADOR",
            "nombre_area": "ADMINISTRACION",
        }
    ]

    def handler(sql, params, cursor):
        if "FROM usuario u" in normalize_sql(sql):
            return [usuario.copy() for usuario in usuarios]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(usuarios_routes, "get_connection", lambda: connection)

    response = client.get("/api/usuarios")
    data = response.get_json()

    assert response.status_code == 200
    assert data == usuarios
    assert connection.closed is True


def test_inicio_del_temporizador(client, fake_connection_factory, monkeypatch, iniciar_sesion):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        if "rt.hora_fin IS NULL" in normalized and "WHERE rt.id_usuario" in normalized:
            return []
        if "SELECT t.id_tarea" in normalized and "WHERE t.id_tarea" in normalized:
            return [{
                "id_tarea": 50,
                "id_cliente": 10,
                "id_area": 1,
                "titulo": "Tarea temporizador",
                "cliente": "Cliente Uno SpA",
                "cliente_rut": "11.111.111-1",
            }]
        if "SELECT valor_hora FROM tarifa_hora" in normalized:
            return [{"valor_hora": Decimal("30000.00")}]
        if "INSERT INTO registro_tiempo" in normalized:
            cursor.lastrowid = 77
            return []
        if "WHERE rt.id_registro = %s" in normalized:
            return [{
                "id_registro": 77,
                "id_tarea": 50,
                "id_cliente": 10,
                "tarea": "Tarea temporizador",
                "cliente": "Cliente Uno SpA",
                "cliente_rut": "11.111.111-1",
                "inicio": "2026-07-12T09:00:00",
                "tarifa_hora": Decimal("30000.00"),
            }]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.post(
        "/api/control-horas/iniciar",
        json={
            "id_usuario": 2,
            "id_tarea": 50,
        },
    )
    data = response.get_json()

    assert response.status_code == 201
    assert data["message"] == "Temporizador iniciado correctamente."
    assert data["temporizador_activo"]["id_registro"] == 77
    assert data["temporizador_activo"]["tarifa_hora"] == 30000.0
    assert connection.transactions == 1
    assert connection.commits == 1


def test_detencion_del_temporizador_registra_horas_y_monto(
    client,
    fake_connection_factory,
    monkeypatch,
    decimal_values,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        if "SELECT id_registro FROM registro_tiempo" in normalized:
            return [{"id_registro": 77}]
        if "UPDATE registro_tiempo SET hora_fin" in normalized:
            return []
        if "SELECT id_registro, duracion_minutos, tarifa_hora, monto" in normalized:
            return [{
                "id_registro": 77,
                "duracion_minutos": decimal_values["ninety_minutes"],
                "tarifa_hora": decimal_values["hourly_rate"],
                "monto": decimal_values["amount"],
            }]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.post(
        "/api/control-horas/detener",
        json={"id_usuario": 2},
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["message"] == "Horas y monto registrados correctamente."
    assert data["registro"]["duracion_minutos"] == 90.0
    assert data["registro"]["tarifa_hora"] == 30000.0
    assert data["registro"]["monto"] == 45000.0
    assert connection.transactions == 1
    assert connection.commits == 1


def test_listado_de_registros_incluye_calculo_de_horas_y_monto(
    client,
    fake_connection_factory,
    monkeypatch,
    decimal_values,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 1,
                "estado": "ACTIVO",
                "nombre_rol": "ADMINISTRADOR",
            }]
        if "u.nombres AS usuario_responsable" in normalized:
            return [{
                "id_registro": 77,
                "tarea": "Tarea temporizador",
                "cliente": "Cliente Uno SpA",
                "inicio": "12-07-2026 09:00:00",
                "fin": "10:30:00",
                "duracion_minutos": decimal_values["ninety_minutes"],
                "tarifa_hora": decimal_values["hourly_rate"],
                "monto": decimal_values["amount"],
                "usuario_responsable": "Usuario Prueba",
            }]
        if "COALESCE(SUM(rt.duracion_minutos), 0) AS minutos_acumulados" in normalized:
            return [{
                "minutos_acumulados": decimal_values["ninety_minutes"],
                "monto_acumulado": decimal_values["amount"],
            }]
        if "c.razon_social AS nombre" in normalized:
            return [{
                "nombre": "Cliente Uno SpA",
                "minutos": decimal_values["ninety_minutes"],
                "monto": decimal_values["amount"],
            }]
        if "t.titulo AS nombre" in normalized:
            return [{
                "nombre": "Tarea temporizador",
                "minutos": decimal_values["ninety_minutes"],
                "monto": decimal_values["amount"],
            }]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.get("/api/control-horas/registros?id_usuario=1")
    data = response.get_json()

    assert response.status_code == 200
    assert data["registros"][0]["duracion_minutos"] == 90.0
    assert data["registros"][0]["tarifa_hora"] == 30000.0
    assert data["registros"][0]["monto"] == 45000.0
    assert data["resumen"]["minutos_acumulados"] == 90.0
    assert data["resumen"]["monto_acumulado"] == 45000.0
    assert data["resumen"]["totales_cliente"][0]["monto"] == 45000.0
    assert data["resumen"]["totales_tarea"][0]["minutos"] == 90.0


def test_endpoint_protegido_sin_sesion_devuelve_401(client):
    response = client.get("/api/usuarios")
    data = response.get_json()

    assert response.status_code == 401
    assert data == {"error": "No autenticado"}


def test_usuario_operativo_no_puede_gestionar_usuarios(client, iniciar_sesion):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    response = client.post(
        "/api/usuarios",
        json={
            "id_rol": 2,
            "id_area": 1,
            "nombres": "Operativo Nuevo",
            "email": "operativo@nahan.test",
            "password": "ClaveTemporal123",
        },
    )
    data = response.get_json()

    assert response.status_code == 403
    assert data == {"error": "No tiene permisos para acceder a este recurso"}


def test_administrador_puede_gestionar_usuarios(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    def handler(sql, params, cursor):
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(usuarios_routes, "get_connection", lambda: connection)
    monkeypatch.setattr(usuarios_routes, "hash_password", lambda password: "hash-controlado")

    response = client.post(
        "/api/usuarios",
        json={
            "id_rol": 2,
            "id_area": 1,
            "nombres": "Operativo Nuevo",
            "email": "operativo@nahan.test",
            "password": "ClaveTemporal123",
        },
    )
    data = response.get_json()

    assert response.status_code == 201
    assert data == {"message": "Usuario registrado correctamente"}
    assert connection.commits == 1


def test_usuario_operativo_no_puede_deshabilitar_cliente(client, iniciar_sesion):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    response = client.patch(
        "/api/clientes/10/deshabilitar",
        json={"id_usuario_auditoria": 999},
    )
    data = response.get_json()

    assert response.status_code == 403
    assert data == {"error": "No tiene permisos para acceder a este recurso"}


def test_administrador_deshabilita_cliente_y_auditoria_usa_sesion(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=7, rol_id=1, area_id=3)

    def handler(sql, params, cursor):
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: connection)

    response = client.patch(
        "/api/clientes/10/deshabilitar",
        json={"id_usuario_auditoria": 999},
    )
    data = response.get_json()

    auditorias = [
        params for sql, params in connection.executed
        if "INSERT INTO auditoria" in normalize_sql(sql)
    ]

    assert response.status_code == 200
    assert data == {"message": "Cliente deshabilitado y registrado en auditoría."}
    assert auditorias == [(7,)]
    assert connection.commits == 1


def test_creacion_de_tarea_usa_usuario_de_sesion_como_creador(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=7, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        if "SELECT id_usuario, estado FROM usuario" in normalize_sql(sql):
            return [(2, "ACTIVO")]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    response = client.post(
        "/api/tareas",
        json={
            "id_cliente": 10,
            "areas": [1],
            "id_responsable": 2,
            "id_creador": 999,
            "titulo": "Tarea con creador de sesión",
            "descripcion": "Prueba",
            "prioridad": "MEDIA",
            "fecha_vencimiento": None,
        },
    )

    inserts = [
        params for sql, params in connection.executed
        if "INSERT INTO tarea" in normalize_sql(sql)
    ]

    assert response.status_code == 201
    assert inserts[0][3] == 7


def test_control_horas_ignora_id_usuario_falso_al_iniciar(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        if "rt.hora_fin IS NULL" in normalized and "WHERE rt.id_usuario" in normalized:
            return []
        if "SELECT t.id_tarea" in normalized and "WHERE t.id_tarea" in normalized:
            return [{
                "id_tarea": 50,
                "id_cliente": 10,
                "id_area": 1,
                "titulo": "Tarea temporizador",
                "cliente": "Cliente Uno SpA",
                "cliente_rut": "11.111.111-1",
            }]
        if "SELECT valor_hora FROM tarifa_hora" in normalized:
            return [{"valor_hora": Decimal("30000.00")}]
        if "INSERT INTO registro_tiempo" in normalized:
            cursor.lastrowid = 77
            return []
        if "WHERE rt.id_registro = %s" in normalized:
            return [{
                "id_registro": 77,
                "id_tarea": 50,
                "id_cliente": 10,
                "tarea": "Tarea temporizador",
                "cliente": "Cliente Uno SpA",
                "cliente_rut": "11.111.111-1",
                "inicio": "2026-07-12T09:00:00",
                "tarifa_hora": Decimal("30000.00"),
            }]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.post(
        "/api/control-horas/iniciar",
        json={
            "id_usuario": 999,
            "id_tarea": 50,
        },
    )

    inserts = [
        params for sql, params in connection.executed
        if "INSERT INTO registro_tiempo" in normalize_sql(sql)
    ]

    assert response.status_code == 201
    assert inserts[0][0] == 2


def test_usuario_operativo_solo_consulta_sus_registros(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        if "COALESCE(SUM(rt.duracion_minutos), 0) AS minutos_acumulados" in normalized:
            return [{"minutos_acumulados": Decimal("0"), "monto_acumulado": Decimal("0")}]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.get("/api/control-horas/registros?id_usuario=999")
    data = response.get_json()

    assert response.status_code == 200
    assert data["registros"] == []
    assert all(999 not in params for _, params in connection.executed)
    assert any(params == (2,) for _, params in connection.executed)


def test_usuario_no_puede_detener_temporizador_ajeno(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        if "SELECT id_registro FROM registro_tiempo" in normalized:
            return []
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.post(
        "/api/control-horas/detener",
        json={"id_usuario": 999},
    )
    data = response.get_json()

    updates = [
        sql for sql, _ in connection.executed
        if "UPDATE registro_tiempo" in normalize_sql(sql)
    ]

    assert response.status_code == 404
    assert data == {"error": "No existe un temporizador activo."}
    assert updates == []


def test_administrador_consulta_horas_de_otro_usuario(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
    decimal_values,
):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 1,
                "estado": "ACTIVO",
                "nombre_rol": "ADMINISTRADOR",
            }]
        if "u.nombres AS usuario_responsable" in normalized:
            return [{
                "id_registro": 77,
                "tarea": "Tarea temporizador",
                "cliente": "Cliente Uno SpA",
                "inicio": "12-07-2026 09:00:00",
                "fin": "10:30:00",
                "duracion_minutos": decimal_values["ninety_minutes"],
                "tarifa_hora": decimal_values["hourly_rate"],
                "monto": decimal_values["amount"],
                "usuario_responsable": "Usuario Prueba",
            }]
        if "COALESCE(SUM(rt.duracion_minutos), 0) AS minutos_acumulados" in normalized:
            return [{
                "minutos_acumulados": decimal_values["ninety_minutes"],
                "monto_acumulado": decimal_values["amount"],
            }]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.get("/api/control-horas/registros?id_usuario=2")
    data = response.get_json()

    assert response.status_code == 200
    assert data["registros"][0]["usuario_responsable"] == "Usuario Prueba"
    assert any(params == (2,) for _, params in connection.executed)


def test_crear_usuario_administrador_asigna_area_administracion(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    connection = fake_connection_factory(lambda sql, params, cursor: [])
    monkeypatch.setattr(usuarios_routes, "get_connection", lambda: connection)
    monkeypatch.setattr(usuarios_routes, "hash_password", lambda password: "hash-controlado")

    response = client.post(
        "/api/usuarios",
        json={
            "id_rol": 1,
            "id_area": 1,
            "nombres": "Admin Nuevo",
            "email": "admin.nuevo@nahan.test",
            "password": "ClaveTemporal123",
        },
    )

    inserts = [
        params for sql, params in connection.executed
        if "INSERT INTO usuario" in normalize_sql(sql)
    ]

    assert response.status_code == 201
    assert inserts[0][0] == 1
    assert inserts[0][1] == 3


def test_crear_usuario_juridico_solo_permite_area_juridica(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    connection = fake_connection_factory(lambda sql, params, cursor: [])
    monkeypatch.setattr(usuarios_routes, "get_connection", lambda: connection)
    monkeypatch.setattr(usuarios_routes, "hash_password", lambda password: "hash-controlado")

    response = client.post(
        "/api/usuarios",
        json={
            "id_rol": 2,
            "id_area": 1,
            "nombres": "Juridico Nuevo",
            "email": "juridico.nuevo@nahan.test",
            "password": "ClaveTemporal123",
        },
    )

    inserts = [
        params for sql, params in connection.executed
        if "INSERT INTO usuario" in normalize_sql(sql)
    ]

    assert response.status_code == 201
    assert inserts[0][0] == 2
    assert inserts[0][1] == 1


def test_crear_usuario_contable_solo_permite_area_contable(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    connection = fake_connection_factory(lambda sql, params, cursor: [])
    monkeypatch.setattr(usuarios_routes, "get_connection", lambda: connection)
    monkeypatch.setattr(usuarios_routes, "hash_password", lambda password: "hash-controlado")

    response = client.post(
        "/api/usuarios",
        json={
            "id_rol": 3,
            "id_area": 2,
            "nombres": "Contable Nuevo",
            "email": "contable.nuevo@nahan.test",
            "password": "ClaveTemporal123",
        },
    )

    inserts = [
        params for sql, params in connection.executed
        if "INSERT INTO usuario" in normalize_sql(sql)
    ]

    assert response.status_code == 201
    assert inserts[0][0] == 3
    assert inserts[0][1] == 2


def test_crear_usuario_juridico_con_area_contable_devuelve_422(client, iniciar_sesion):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    response = client.post(
        "/api/usuarios",
        json={
            "id_rol": 2,
            "id_area": 2,
            "nombres": "Juridico Mal Area",
            "email": "juridico.mal@nahan.test",
            "password": "ClaveTemporal123",
        },
    )
    data = response.get_json()

    assert response.status_code == 422
    assert data == {"error": "El rol seleccionado solo permite Área jurídica"}


def test_crear_usuario_contable_con_area_juridica_devuelve_422(client, iniciar_sesion):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    response = client.post(
        "/api/usuarios",
        json={
            "id_rol": 3,
            "id_area": 1,
            "nombres": "Contable Mal Area",
            "email": "contable.mal@nahan.test",
            "password": "ClaveTemporal123",
        },
    )
    data = response.get_json()

    assert response.status_code == 422
    assert data == {"error": "El rol seleccionado solo permite Área contable"}


def test_modificar_usuario_valida_coherencia_entre_rol_y_area(client, iniciar_sesion):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    response = client.put(
        "/api/usuarios/10",
        json={
            "id_rol": 2,
            "id_area": 2,
            "nombres": "Usuario Existente",
            "email": "usuario.existente@nahan.test",
            "estado": "ACTIVO",
        },
    )
    data = response.get_json()

    assert response.status_code == 422
    assert data == {"error": "El rol seleccionado solo permite Área jurídica"}


def test_asignar_rol_actualiza_area_derivada(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    connection = fake_connection_factory(lambda sql, params, cursor: [])
    monkeypatch.setattr(usuarios_routes, "get_connection", lambda: connection)

    response = client.put("/api/usuarios/10/rol", json={"id_rol": 3})

    updates = [
        params for sql, params in connection.executed
        if "UPDATE usuario SET id_rol" in normalize_sql(sql)
    ]

    assert response.status_code == 200
    assert updates == [(3, 2, 10)]


def test_usuario_no_administrador_no_puede_modificar_roles_ni_areas(
    client,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    response = client.put(
        "/api/usuarios/10",
        json={
            "id_rol": 1,
            "id_area": 3,
            "nombres": "Intento Operativo",
            "email": "intento@nahan.test",
            "estado": "ACTIVO",
        },
    )

    assert response.status_code == 403


def test_usuario_juridico_puede_usar_estado_operativo(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    connection = fake_connection_factory(lambda sql, params, cursor: [])
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    response = client.put("/api/tareas/50/estado", json={"estado": "EN_PROCESO"})

    assert response.status_code == 200
    assert any(params == ("EN_PROCESO", 50) for _, params in connection.executed)


def test_usuario_contable_puede_usar_estado_operativo(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=3, rol_id=3, area_id=2)

    connection = fake_connection_factory(lambda sql, params, cursor: [])
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    response = client.put("/api/tareas/51/estado", json={"estado": "EN_REVISION"})

    assert response.status_code == 200
    assert any(params == ("EN_REVISION", 51) for _, params in connection.executed)


def test_usuario_juridico_no_puede_cancelar_tarea(client, iniciar_sesion):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    response = client.put("/api/tareas/50/estado", json={"estado": "CANCELADA"})
    data = response.get_json()

    assert response.status_code == 403
    assert data == {"error": "Solo un administrador puede aplicar estados finales"}


def test_usuario_contable_no_puede_completar_tarea(client, iniciar_sesion):
    iniciar_sesion(usuario_id=3, rol_id=3, area_id=2)

    response = client.put("/api/tareas/51/estado", json={"estado": "COMPLETADA"})
    data = response.get_json()

    assert response.status_code == 403
    assert data == {"error": "Solo un administrador puede aplicar estados finales"}


def test_administrador_puede_cancelar_tarea(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    connection = fake_connection_factory(lambda sql, params, cursor: [])
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    response = client.put("/api/tareas/52/estado", json={"estado": "CANCELADA"})

    assert response.status_code == 200
    assert any(params == ("CANCELADA", 52) for _, params in connection.executed)


def test_administrador_puede_completar_tarea(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    connection = fake_connection_factory(lambda sql, params, cursor: [])
    monkeypatch.setattr(tareas_routes, "get_connection", lambda: connection)

    response = client.put("/api/tareas/53/estado", json={"estado": "COMPLETADA"})

    assert response.status_code == 200
    assert any(params == ("COMPLETADA", 53) for _, params in connection.executed)


def test_rol_falso_enviado_no_autoriza_estado_final(client, iniciar_sesion):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    response = client.put(
        "/api/tareas/54/estado",
        json={
            "estado": "CANCELADA",
            "rol": "ADMINISTRADOR",
        },
    )

    assert response.status_code == 403


def test_estado_final_enviado_directamente_por_operativo_devuelve_403(
    client,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=3, rol_id=3, area_id=2)

    response = client.put("/api/tareas/55/estado", json={"estado": "COMPLETADA"})

    assert response.status_code == 403


def test_control_horas_inicio_sin_tarea_devuelve_400(client, monkeypatch, iniciar_sesion):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def fail_connection():
        raise AssertionError("No debe abrir conexión si falta la tarea")

    monkeypatch.setattr(control_horas_routes, "get_connection", fail_connection)

    response = client.post("/api/control-horas/iniciar", json={})
    data = response.get_json()

    assert response.status_code == 400
    assert data == {"error": "Debe seleccionar una tarea válida."}


def test_control_horas_inicio_con_tarea_inexistente_devuelve_404(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        if "rt.hora_fin IS NULL" in normalized:
            return []
        if "SELECT t.id_tarea" in normalized and "WHERE t.id_tarea" in normalized:
            return []
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.post("/api/control-horas/iniciar", json={"id_tarea": 999})
    data = response.get_json()

    inserts = [
        sql for sql, _ in connection.executed
        if "INSERT INTO registro_tiempo" in normalize_sql(sql)
    ]

    assert response.status_code == 404
    assert data == {"error": "La tarea no existe o no está disponible para este usuario."}
    assert inserts == []
    assert connection.rollbacks == 1


def test_control_horas_inicio_filtra_tarea_inactiva_o_finalizada(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        if "rt.hora_fin IS NULL" in normalized:
            return []
        if "SELECT t.id_tarea" in normalized and "WHERE t.id_tarea" in normalized:
            assert "t.estado IN ('PENDIENTE', 'EN_PROCESO', 'EN_REVISION')" in normalized
            assert "c.estado = 'ACTIVO'" in normalized
            return []
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.post("/api/control-horas/iniciar", json={"id_tarea": 50})

    assert response.status_code == 404
    assert connection.rollbacks == 1


def test_control_horas_no_permite_dos_temporizadores_activos(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        if "rt.hora_fin IS NULL" in normalized:
            return [{
                "id_registro": 77,
                "id_tarea": 50,
                "id_cliente": 10,
                "tarea": "Tarea activa",
                "descripcion": "En curso",
                "cliente": "Cliente Uno SpA",
                "cliente_rut": "11.111.111-1",
                "inicio": "2026-07-12T09:00:00",
                "tarifa_hora": Decimal("30000.00"),
                "estado": "EN_CURSO",
            }]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.post("/api/control-horas/iniciar", json={"id_tarea": 51})
    data = response.get_json()

    inserts = [
        sql for sql, _ in connection.executed
        if "INSERT INTO registro_tiempo" in normalize_sql(sql)
    ]

    assert response.status_code == 409
    assert data == {"error": "Ya existe un temporizador activo para este usuario."}
    assert inserts == []
    assert connection.rollbacks == 1


def test_control_horas_contexto_recupera_temporizador_activo(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        if "ORDER BY c.razon_social ASC, t.titulo ASC" in normalized:
            return [{
                "id_tarea": 50,
                "id_cliente": 10,
                "titulo": "Tarea temporizador",
                "descripcion": "Descripción real",
                "cliente": "Cliente Uno SpA",
                "cliente_rut": "11.111.111-1",
            }]
        if "rt.hora_fin IS NULL" in normalized:
            return [{
                "id_registro": 77,
                "id_tarea": 50,
                "id_cliente": 10,
                "tarea": "Tarea temporizador",
                "descripcion": "Descripción real",
                "cliente": "Cliente Uno SpA",
                "cliente_rut": "11.111.111-1",
                "inicio": "2026-07-12T09:00:00",
                "tarifa_hora": Decimal("30000.00"),
                "estado": "EN_CURSO",
            }]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.get("/api/control-horas/contexto")
    data = response.get_json()

    assert response.status_code == 200
    assert data["temporizador_activo"]["id_registro"] == 77
    assert data["temporizador_activo"]["activo"] is True
    assert data["temporizador_activo"]["inicio"] == "2026-07-12T09:00:00"


def test_control_horas_contexto_sin_temporizador_activo(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.get("/api/control-horas/contexto")
    data = response.get_json()

    assert response.status_code == 200
    assert data["temporizador_activo"] is None
    assert data["tareas"] == []


def test_control_horas_detencion_devuelve_resumen_actualizado(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
    decimal_values,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        if "SELECT id_registro FROM registro_tiempo" in normalized:
            return [{"id_registro": 77}]
        if "UPDATE registro_tiempo SET hora_fin" in normalized:
            return []
        if "SELECT id_registro, duracion_minutos, tarifa_hora, monto" in normalized:
            return [{
                "id_registro": 77,
                "duracion_minutos": decimal_values["ninety_minutes"],
                "tarifa_hora": decimal_values["hourly_rate"],
                "monto": decimal_values["amount"],
                "tarea": "Tarea temporizador",
                "descripcion": "Descripción",
                "cliente": "Cliente Uno SpA",
                "fecha": "12-07-2026",
                "inicio": "09:00:00",
                "fin": "10:30:00",
            }]
        if "COUNT(*) AS total_registros" in normalized:
            return [{
                "minutos_acumulados": decimal_values["ninety_minutes"],
                "monto_acumulado": decimal_values["amount"],
                "minutos_hoy": decimal_values["ninety_minutes"],
                "total_registros": 1,
            }]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.post("/api/control-horas/detener")
    data = response.get_json()

    assert response.status_code == 200
    assert data["registro"]["duracion_minutos"] == 90.0
    assert data["registro"]["monto"] == 45000.0
    assert data["resumen"]["minutos_hoy"] == 90.0
    assert data["resumen"]["total_registros"] == 1
    assert connection.commits == 1


def test_control_horas_detencion_sin_temporizador_activo_devuelve_404(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=3, rol_id=3, area_id=2)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 3,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_CONTABLE",
            }]
        if "SELECT id_registro FROM registro_tiempo" in normalized:
            return []
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.post("/api/control-horas/detener", json={"id_usuario": 999})
    data = response.get_json()

    assert response.status_code == 404
    assert data == {"error": "No existe un temporizador activo."}
    assert connection.rollbacks == 1


def test_control_horas_detencion_hace_rollback_ante_error(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        if "SELECT id_registro FROM registro_tiempo" in normalized:
            return [{"id_registro": 77}]
        if "UPDATE registro_tiempo SET hora_fin" in normalized:
            raise RuntimeError("fallo controlado")
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.post("/api/control-horas/detener")

    assert response.status_code == 500
    assert connection.rollbacks == 1
    assert connection.commits == 0


def test_control_horas_historial_incluye_resumen_hoy_y_total_registros(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
    decimal_values,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 2,
                "estado": "ACTIVO",
                "nombre_rol": "USUARIO_AREA_JURIDICA",
            }]
        if "u.nombres AS usuario_responsable" in normalized:
            return []
        if "COUNT(*) AS total_registros" in normalized:
            return [{
                "minutos_acumulados": decimal_values["ninety_minutes"],
                "monto_acumulado": decimal_values["amount"],
                "minutos_hoy": Decimal("30.00"),
                "total_registros": 3,
            }]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.get("/api/control-horas/registros?id_usuario=999")
    data = response.get_json()

    assert response.status_code == 200
    assert data["resumen"]["minutos_hoy"] == 30.0
    assert data["resumen"]["total_registros"] == 3
    assert any(params == (2,) for _, params in connection.executed)


def test_control_horas_administrador_mantiene_consulta_autorizada_de_otro_usuario(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3)

    def handler(sql, params, cursor):
        normalized = normalize_sql(sql)
        if "SELECT u.id_usuario, u.estado, r.nombre_rol" in normalized:
            return [{
                "id_usuario": 1,
                "estado": "ACTIVO",
                "nombre_rol": "ADMINISTRADOR",
            }]
        if "COUNT(*) AS total_registros" in normalized:
            return [{
                "minutos_acumulados": Decimal("0"),
                "monto_acumulado": Decimal("0"),
                "minutos_hoy": Decimal("0"),
                "total_registros": 0,
            }]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(control_horas_routes, "get_connection", lambda: connection)

    response = client.get("/api/control-horas/registros?id_usuario=3")

    assert response.status_code == 200
    assert any(params == (3,) for _, params in connection.executed)


def test_navegacion_mantiene_unico_modulo_operativo_clientes():
    source = (ROOT_DIR / "frontend/assets/js/navigation.js").read_text()

    assert 'href: "../clientes/listar_clientes.html"' in source
    assert "Gestión de clientes" not in source
    assert "clientes-admin" not in source


def test_administrador_puede_ver_opcion_quitar_cliente():
    source = (ROOT_DIR / "frontend/clientes/listar_clientes.js").read_text()
    admin_block = source.split("if (esAdmin) {", 1)[1]

    assert 'usuarioActual.nombre_rol === "ADMINISTRADOR"' in source
    assert "eliminar_cliente.html?id=${cliente.id_cliente}" in admin_block


def test_juridico_no_recibe_opcion_quitar_cliente():
    source = (ROOT_DIR / "frontend/clientes/listar_clientes.js").read_text()
    before_admin_block = source.split("if (esAdmin) {", 1)[0]

    assert "localStorage" not in source
    assert "eliminar_cliente.html?id=${cliente.id_cliente}" not in before_admin_block


def test_contable_no_recibe_opcion_quitar_cliente():
    source = (ROOT_DIR / "frontend/clientes/listar_clientes.js").read_text()

    assert "obtenerUsuarioActual()" in source
    assert source.count("eliminar_cliente.html?id=${cliente.id_cliente}") == 1
    assert "if (esAdmin) {" in source


def test_juridico_obtiene_403_al_eliminar_cliente_directamente(
    client,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1)

    def fail_connection():
        raise AssertionError("No debe abrir conexión para usuarios sin permiso")

    monkeypatch.setattr(clientes_routes, "get_connection", fail_connection)

    response = client.delete("/api/clientes/10/eliminar-definitivo")

    assert response.status_code == 403


def test_contable_obtiene_403_al_deshabilitar_cliente_directamente(
    client,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=3, rol_id=3, area_id=2)

    def fail_connection():
        raise AssertionError("No debe abrir conexión para usuarios sin permiso")

    monkeypatch.setattr(clientes_routes, "get_connection", fail_connection)

    response = client.patch("/api/clientes/10/deshabilitar")

    assert response.status_code == 403


def test_administrador_puede_eliminar_cliente_definitivamente(
    client,
    fake_connection_factory,
    monkeypatch,
    iniciar_sesion,
):
    iniciar_sesion(usuario_id=7, rol_id=1, area_id=3)

    def handler(sql, params, cursor):
        if "SELECT rut, razon_social FROM cliente" in normalize_sql(sql):
            return [("11.111.111-1", "Cliente Prueba SpA")]
        return []

    connection = fake_connection_factory(handler)
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: connection)

    response = client.delete("/api/clientes/10/eliminar-definitivo")
    data = response.get_json()

    deletes = [
        params for sql, params in connection.executed
        if "DELETE FROM cliente WHERE id_cliente" in normalize_sql(sql)
    ]
    auditorias = [
        params for sql, params in connection.executed
        if "INSERT INTO auditoria" in normalize_sql(sql)
    ]

    assert response.status_code == 200
    assert data == {"message": "Cliente eliminado físicamente y registrado en auditoría."}
    assert deletes == [(10,)]
    assert auditorias[0][0] == 7
    assert connection.commits == 1
