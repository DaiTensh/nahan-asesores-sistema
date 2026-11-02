"""Validación de RUT, correo y teléfono al registrar y modificar clientes (RF01, RF04)."""
import pytest

import backend.routes.clientes_routes as clientes_routes
from backend.utils.validaciones_cliente import (
    error_de_contacto, normalizar_rut, rut_comparable,
)


@pytest.mark.parametrize("texto,esperado", [
    ("12.345.678-5", "12.345.678-5"), ("12345678-5", "12.345.678-5"), ("12345678 5".replace(" ", "-"), "12.345.678-5"),
    ("123456785", "12.345.678-5"), ("  12.345.678-5 ", "12.345.678-5"), ("1.234.567-k", "1.234.567-K"),
    ("76.543.210-9", "76.543.210-9"), ("7.654.321-0", "7.654.321-0"),
])
def test_el_rut_se_normaliza_a_un_unico_formato(texto, esperado):
    assert normalizar_rut(texto) == esperado


@pytest.mark.parametrize("texto", ["", None, "99", "1-9", "abc", "12.345.67-5", "12.345.678-55", "12..345.678-5", "12.345.678-x",
                                   "123.456.789-0", "12.345.678-5; DROP TABLE cliente", "12.345.678-5\nx",
                                   "١٢.٣٤٥.٦٧٨-٥"])
def test_un_rut_con_formato_invalido_se_rechaza(texto):
    assert normalizar_rut(texto) is None


def test_ruts_equivalentes_tienen_la_misma_forma_comparable():
    assert {rut_comparable(normalizar_rut(t)) for t in ("12.345.678-5", "12345678-5", "123456785")} == {"123456785"}
    assert rut_comparable("1.234.567-K") == "1234567K"


@pytest.mark.parametrize("correo,telefono,ok", [
    ("", "", True), ("a@b.cl", "+56 9 1234 5678", True), ("nombre.apellido@empresa.cl", "(2) 2345-6789", True),
    ("sin-arroba", "", False), ("a@b", "", False), ("a b@c.cl", "", False), ("a@b.cl" + "x" * 150, "", False),
    ("", "abc", False), ("", "12", False), ("", "+56 9 1234 5678 9999 0000", False), ("", "<script>", False),
])
def test_correo_y_telefono_opcionales_pero_con_formato(correo, telefono, ok):
    assert (error_de_contacto(correo, telefono) is None) is ok


def _registrar(client, **datos):
    base = {"rut": "12.345.678-5", "razon_social": "Cliente S.A.", "email": "a@b.cl", "telefono": "+56 9 1234 5678", "areas": [1]}
    return client.post("/api/clientes", json={**base, **datos})


@pytest.mark.parametrize("campo,valor,mensaje", [
    ("rut", "99", "RUT no tiene un formato válido"), ("rut", "", "obligatorios"),
    ("email", "no-es-correo", "correo"), ("telefono", "abc", "teléfono"),
])
def test_registrar_rechaza_datos_invalidos_antes_de_tocar_la_base(client, iniciar_sesion, monkeypatch, campo, valor, mensaje):
    iniciar_sesion()
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: pytest.fail("no debe abrir la base"))
    respuesta = _registrar(client, **{campo: valor})
    assert respuesta.status_code == 400 and mensaje in respuesta.get_json()["error"]


def test_registrar_guarda_el_rut_normalizado_y_compara_sin_importar_el_formato(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion()
    sentencias = []

    def handler(sql, params, cursor):
        sentencias.append((" ".join(sql.split()), params))
        if sql.lstrip().startswith("SELECT id_cliente"):
            return []
        cursor.lastrowid = 7
        return []
    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: conexion)

    respuesta = _registrar(client, rut="12345678-5")
    assert respuesta.status_code == 201
    consulta, parametros = sentencias[0]
    assert "REPLACE(REPLACE(UPPER(rut)" in consulta and parametros == ("123456785",)
    insercion = next(p for s, p in sentencias if s.startswith("INSERT INTO cliente "))
    assert insercion[0] == "12.345.678-5"


def test_un_rut_ya_registrado_en_otro_formato_se_detecta_como_duplicado(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion()

    def handler(sql, params, cursor):
        return [(3,)] if sql.lstrip().startswith("SELECT id_cliente") else []
    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: conexion)
    respuesta = _registrar(client, rut="12345678-5")
    assert respuesta.status_code == 400 and "ya pertenece" in respuesta.get_json()["error"]
    assert conexion.commits == 0


@pytest.mark.parametrize("campo,valor", [("email", "no-es-correo"), ("telefono", "abc")])
def test_modificar_rechaza_contacto_invalido(client, iniciar_sesion, monkeypatch, campo, valor):
    iniciar_sesion()
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: pytest.fail("no debe abrir la base"))
    cuerpo = {"razon_social": "Cliente S.A.", "email": "a@b.cl", "telefono": "+56 9 1234 5678", "areas": [1], campo: valor}
    assert client.put("/api/clientes/1", json=cuerpo).status_code == 400


@pytest.mark.parametrize("fila_existente,estado,mensaje", [
    ((1,), 409, "ya se encuentra deshabilitado"),
    (None, 404, "inexistente"),
])
def test_deshabilitar_distingue_cliente_ya_inactivo_de_inexistente(client, iniciar_sesion, monkeypatch, fake_connection_factory,
                                                                    fila_existente, estado, mensaje):
    """MySQL informa 0 filas afectadas al «actualizar» un cliente que ya estaba INACTIVO."""
    iniciar_sesion(usuario_id=1, rol_id=1)
    conexion_ref = {}

    def handler(sql, params, cursor):
        if sql.startswith("UPDATE cliente"):
            cursor.rowcount = 0
            return []
        if sql.startswith("SELECT estado FROM cliente"):
            return [fila_existente] if fila_existente else []
        return []
    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: conexion)
    respuesta = client.patch("/api/clientes/10/deshabilitar")
    assert respuesta.status_code == estado and mensaje in respuesta.get_json()["error"].lower()
    assert conexion.commits == 0
