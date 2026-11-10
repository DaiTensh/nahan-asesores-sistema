"""CSRF: defensa en profundidad por cabecera Origin (además de SameSite=Lax)."""
import pytest

from backend.app import _origen_permitido

H = {"Content-Type": "application/json"}


@pytest.mark.parametrize("origen,host,permitidos,esperado", [
    ("https://nahan.ejemplo.invalid", "nahan.ejemplo.invalid", [], True),
    ("http://nahan.ejemplo.invalid:8080", "nahan.ejemplo.invalid", [], True),   # túnel SSH / puerto distinto
    ("http://localhost:8080", "localhost", [], True),
    ("https://otro.ejemplo.invalid", "nahan.ejemplo.invalid", [], False),
    ("https://nahan.ejemplo.invalid.atacante.invalid", "nahan.ejemplo.invalid", [], False),
    ("null", "nahan.ejemplo.invalid", [], False),
    ("https://front.ejemplo.invalid", "api.ejemplo.invalid", ["https://front.ejemplo.invalid"], True),
    ("http://[::1]:5000", "[::1]:5000", [], True),
])
def test_origen_permitido(origen, host, permitidos, esperado):
    assert _origen_permitido(origen, host, permitidos) is esperado


def test_escritura_desde_otro_sitio_se_rechaza_con_403(client, iniciar_sesion):
    iniciar_sesion()
    r = client.post("/api/tareas", json={}, headers={"Origin": "https://atacante.invalid"})
    assert r.status_code == 403
    for metodo in ("put", "patch", "delete"):
        assert getattr(client, metodo)("/api/tareas/1", headers={"Origin": "https://atacante.invalid"}).status_code == 403


def test_login_desde_otro_sitio_tambien_se_rechaza(client):
    r = client.post("/api/login", json={"email": "a@b.cl", "password": "x"}, headers={"Origin": "https://atacante.invalid"})
    assert r.status_code == 403


def test_sec_fetch_site_cross_site_sin_origin_se_rechaza(client):
    assert client.post("/api/login", json={}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_mismo_origen_y_sin_origen_no_se_ven_afectados(client, iniciar_sesion):
    iniciar_sesion()
    # El cliente de pruebas usa Host «localhost»: el mismo origen pasa y la solicitud llega a la validación normal (400).
    assert client.post("/api/tareas", json={}, headers={"Origin": "http://localhost"}).status_code == 400
    assert client.post("/api/tareas", json={}).status_code == 400


def test_las_lecturas_no_se_comprueban(client, iniciar_sesion):
    iniciar_sesion()
    assert client.get("/api/auth/me", headers={"Origin": "https://atacante.invalid"}).status_code == 200


def test_se_puede_desactivar_por_configuracion(client, monkeypatch):
    monkeypatch.setenv("CSRF_COMPROBAR_ORIGEN", "false")
    r = client.post("/api/login", json={"email": "a@b.cl", "password": "x"}, headers={"Origin": "https://atacante.invalid"})
    assert r.status_code != 403


def test_el_origen_de_desarrollo_con_live_server_sigue_permitido(client, monkeypatch):
    # Front en http://localhost:5500 y API en 127.0.0.1:5000 (frontend/assets/js/api_config.js).
    r = client.post("/api/login", json={"email": "a@b.cl", "password": "x"}, base_url="http://127.0.0.1:5000",
                    headers={"Origin": "http://localhost:5500"})
    assert r.status_code != 403
