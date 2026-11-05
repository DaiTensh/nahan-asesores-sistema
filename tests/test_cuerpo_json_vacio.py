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


@pytest.mark.parametrize("metodo,ruta", [
    ("post", "/api/clientes"),
    ("put", "/api/clientes/1"),
    ("post", "/api/clientes/1/cambiar-estado"),
    ("post", "/api/clientes/1/observaciones"),
    ("post", "/api/clientes/1/documentos"),
])
@pytest.mark.parametrize("encabezados", [{}, JSON], ids=["sin tipo de contenido", "JSON sin cuerpo"])
def test_un_cuerpo_ausente_es_un_error_del_cliente_no_un_500(client, iniciar_sesion, metodo, ruta, encabezados):
    """`request.json` lanzaba dentro del `try` general y el usuario recibía «error interno» con una traza en el registro."""
    iniciar_sesion(usuario_id=1, rol_id=1)
    respuesta = getattr(client, metodo)(ruta, headers=encabezados)
    assert 400 <= respuesta.status_code < 500, (respuesta.status_code, respuesta.get_json())


def test_los_errores_http_genericos_de_la_api_salen_en_espanol(client):
    """Werkzeug los redacta en inglés («The requested URL was not found on the server...»)."""
    inexistente = client.get("/api/no-existe")
    metodo = client.delete("/api/clientes")

    assert inexistente.status_code == 404 and inexistente.get_json() == {"error": "El recurso solicitado no existe."}
    assert metodo.status_code == 405 and metodo.get_json() == {"error": "Método no permitido para este recurso."}
