"""El filtro global de cuerpos JSON no debe rechazar una solicitud sin cuerpo.

Regresión: el frontend enviaba «Content-Type: application/json» sin cuerpo al
detener el temporizador (RF71-RF75) y al deshabilitar o eliminar clientes (RF03),
y la API respondía 400 «El cuerpo debe ser un objeto JSON válido» antes de llegar
a la lógica de cada ruta.
"""
import pytest

JSON = {"Content-Type": "application/json"}


def test_una_solicitud_json_sin_cuerpo_llega_a_la_ruta(client):
    respuesta = client.post("/api/logout", headers=JSON)
    assert respuesta.status_code != 400 or "objeto JSON" not in respuesta.get_json().get("error", "")


@pytest.mark.parametrize("metodo,ruta", [
    ("post", "/api/control-horas/detener"),
    ("patch", "/api/clientes/1/deshabilitar"),
    ("delete", "/api/clientes/1/eliminar-definitivo"),
])
def test_las_acciones_sin_datos_no_se_rechazan_por_el_filtro_de_cuerpo(client, metodo, ruta):
    respuesta = getattr(client, metodo)(ruta, headers=JSON)
    assert respuesta.status_code == 401, "se evalúa la autenticación, no el cuerpo"
    assert respuesta.get_json()["error"] == "No autenticado"


@pytest.mark.parametrize("cuerpo", ["[1, 2]", '"texto"', "5", "no es json", "null"])
def test_un_cuerpo_json_que_no_es_un_objeto_sigue_rechazandose(client, cuerpo):
    respuesta = client.post("/api/login", data=cuerpo, headers=JSON)
    assert respuesta.status_code == 400
    assert respuesta.get_json()["error"] == "El cuerpo debe ser un objeto JSON válido"


def test_un_objeto_vacio_se_sigue_aceptando(client):
    assert "objeto JSON" not in str(client.post("/api/logout", json={}).get_json())
