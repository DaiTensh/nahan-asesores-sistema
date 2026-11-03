"""RUT chileno: dígito verificador (módulo 11), normalización y coherencia entre servidor, interfaz y datos de demostración."""
import json
import os
import random
import re
import shutil
import subprocess
import sys

import pytest

import backend.routes.clientes_routes as clientes_routes
from backend.utils.validaciones_cliente import (
    MENSAJE_RUT, MENSAJE_RUT_DIGITO, calcular_digito_verificador, rut_comparable, validar_rut,
)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize("cuerpo,digito", [
    (12345678, "5"), (11111111, "1"), (22222222, "2"), (99999999, "9"), (1234567, "4"), (1000000, "9"), (5000000, "1"),
    (25000000, "6"), (12000008, "K"), (12000011, "K"), (12000002, "0"), (12000016, "0"), (7654321, "6"), (76543210, "3"),
])
def test_digito_verificador_de_referencia(cuerpo, digito):
    assert calcular_digito_verificador(cuerpo) == digito
    assert calcular_digito_verificador(str(cuerpo)) == digito


@pytest.mark.parametrize("texto,esperado", [
    ("12.345.678-5", "12.345.678-5"), ("12345678-5", "12.345.678-5"), ("123456785", "12.345.678-5"), (" 12.345.678-5 ", "12.345.678-5"),
    ("12.000.008-K", "12.000.008-K"), ("12.000.008-k", "12.000.008-K"), ("12000008k", "12.000.008-K"), ("12.000.002-0", "12.000.002-0"),
    ("1.234.567-4", "1.234.567-4"), ("1234567-4", "1.234.567-4"), ("01.234.567-4", "1.234.567-4"), ("99.999.999-9", "99.999.999-9"),
    ("76.543.210-3", "76.543.210-3"), ("1.000.000-9", "1.000.000-9"),
])
def test_ruts_validos_en_cualquier_formato_se_normalizan(texto, esperado):
    assert validar_rut(texto) == (esperado, None)


@pytest.mark.parametrize("texto", ["12.345.678-9", "12.345.678-4", "12.345.678-K", "12.345.678-0", "1.234.567-K", "76.543.210-9",
                                   "12.000.008-0", "12.000.002-K", "11.111.111-2", "99.999.999-0"])
def test_un_digito_verificador_incorrecto_se_rechaza(texto):
    assert validar_rut(texto) == (None, MENSAJE_RUT_DIGITO)


@pytest.mark.parametrize("texto", ["", None, "99", "1-9", "abc", "12.345.67-5", "12..345.678-5", "12.345.678-55", "123.456.789-0",
                                   "12.345.678-5; DROP", "12.345.678-5\nx", "١٢.٣٤٥.٦٧٨-٥", "12 345 678-5", "12,345,678-5"])
def test_un_formato_invalido_se_rechaza(texto):
    assert validar_rut(texto) == (None, MENSAJE_RUT)


@pytest.mark.parametrize("texto", ["0.000.000-0", "00.000.000-0", "0.999.999-0", "0.000.001-9"])
def test_un_cuerpo_menor_al_minimo_no_es_un_rut(texto):
    assert validar_rut(texto)[0] is None


def test_el_mismo_rut_en_distinto_formato_tiene_una_sola_forma_comparable():
    formas = {rut_comparable(validar_rut(t)[0]) for t in ("12.345.678-5", "12345678-5", "123456785", "12.345.678-5 ")}
    assert formas == {"123456785"}
    assert rut_comparable(validar_rut("12.000.008-k")[0]) == "12000008K"


def test_todo_cuerpo_con_su_digito_calculado_es_valido_y_ninguno_con_otro_digito():
    azar = random.Random(74)
    for _ in range(3000):
        cuerpo = azar.randint(1_000_000, 99_999_999)
        digito = calcular_digito_verificador(cuerpo)
        assert validar_rut(f"{cuerpo}-{digito}")[1] is None
        otros = [d for d in "0123456789K" if d != digito]
        assert validar_rut(f"{cuerpo}-{azar.choice(otros)}")[1] == MENSAJE_RUT_DIGITO


# --- registro de clientes (API) ------------------------------------------------

def registrar(client, **datos):
    base = {"rut": "12.345.678-5", "razon_social": "Cliente S.A.", "email": "a@b.cl", "telefono": "+56 9 1234 5678", "areas": [1]}
    return client.post("/api/clientes", json={**base, **datos})


@pytest.mark.parametrize("rut,mensaje", [("12.345.678-9", "dígito verificador"), ("99", "formato válido"), ("11.111.111-2", "dígito verificador")])
def test_la_api_rechaza_un_rut_con_digito_incorrecto_antes_de_tocar_la_base(client, iniciar_sesion, monkeypatch, rut, mensaje):
    iniciar_sesion()
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: pytest.fail("no debe abrir la base"))
    respuesta = registrar(client, rut=rut)
    assert respuesta.status_code == 400 and mensaje in respuesta.get_json()["error"]


def test_la_api_guarda_el_rut_normalizado_aunque_llegue_en_minusculas(client, iniciar_sesion, monkeypatch, fake_connection_factory):
    iniciar_sesion()
    capturado = []

    def handler(sql, params, cursor):
        capturado.append((" ".join(sql.split()), params))
        cursor.lastrowid = 9
        return []
    conexion = fake_connection_factory(handler)
    monkeypatch.setattr(clientes_routes, "get_connection", lambda: conexion)
    assert registrar(client, rut="12000008k").status_code == 201
    assert next(p for s, p in capturado if s.startswith("INSERT INTO cliente "))[0] == "12.000.008-K"
    assert next(p for s, p in capturado if "REPLACE(REPLACE(UPPER(rut)" in s) == ("12000008K",)


# --- coherencia con la interfaz -------------------------------------------------

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
def test_la_validacion_del_navegador_coincide_con_la_del_servidor():
    """Se ejecuta rut.js con Node sobre cientos de RUT y se compara con validar_rut."""
    azar = random.Random(11)
    muestras = ["12.345.678-5", "12345678-5", "12.000.008-k", "12.000.008-K", "12.345.678-9", "99", "", "1-9", "0.000.000-0", "01.234.567-4",
                "1.000.000-9", "12.345.678-5; x", "76.543.210-9", "76.543.210-3", "99.999.999-9", " 12.345.678-5 ", "12 345 678-5"]
    for _ in range(600):
        cuerpo = azar.randint(900_000, 99_999_999)
        digito = azar.choice([calcular_digito_verificador(cuerpo), azar.choice("0123456789Kk")])
        muestras.append(azar.choice([f"{cuerpo}-{digito}", f"{cuerpo:,}".replace(",", ".") + f"-{digito}", f"{cuerpo}{digito}"]))
    guion = (
        "global.window = {}; require(process.argv[1]);"
        "const m = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "console.log(JSON.stringify(m.map(t => { const r = window.Rut.validar(t); return [r.valido, r.canonico]; })));"
    )
    salida = subprocess.run([NODE, "-e", guion, os.path.join(RAIZ, "frontend", "assets", "js", "rut.js")], input=json.dumps(muestras),
                            capture_output=True, text=True, timeout=60, check=True).stdout
    navegador = json.loads(salida)
    servidor = [[validar_rut(t)[1] is None, validar_rut(t)[0]] for t in muestras]
    assert navegador == servidor
    assert sum(1 for valido, _ in servidor if valido) > 100 and sum(1 for valido, _ in servidor if not valido) > 100


def test_el_formulario_de_registro_valida_el_rut_antes_de_confirmar_y_envia_el_normalizado():
    js = open(os.path.join(RAIZ, "frontend", "clientes", "registrar_clientes.js"), encoding="utf-8").read()
    html = open(os.path.join(RAIZ, "frontend", "clientes", "registrar_clientes.html"), encoding="utf-8").read()
    assert js.index("window.Rut.validar(") < js.index('confirm("¿Desea crear este cliente?")')
    assert "rut: validacionRut.canonico" in js
    assert html.index("assets/js/rut.js") < html.index("registrar_clientes.js")
    ejemplo = re.search(r'id="rut"[^>]*placeholder="([^"]+)"', html).group(1)
    assert validar_rut(ejemplo) == (ejemplo, None), "el ejemplo del formulario debe ser un RUT válido"


# --- datos de demostración ---------------------------------------------------------

def test_todos_los_rut_de_la_siembra_son_validos_distintos_y_normalizados():
    sys.path.insert(0, os.path.join(RAIZ, "database"))
    import seed_dev
    ruts = [c[0] for c in seed_dev.CLIENTES]
    assert len(set(ruts)) == len(ruts) == 6
    assert [validar_rut(r) for r in ruts] == [(r, None) for r in ruts]
    assert {t[0] for t in seed_dev.TAREAS} <= set(ruts), "cada tarea sembrada apunta a un cliente que existe"


def test_los_rut_anteriores_de_la_siembra_se_corrigen_a_otros_validos_de_la_siembra():
    import seed_dev
    nuevos = {c[0] for c in seed_dev.CLIENTES}
    for anterior, nuevo in seed_dev.RUT_ANTERIORES.items():
        assert validar_rut(anterior)[1] == MENSAJE_RUT_DIGITO, f"{anterior} era inválido"
        assert validar_rut(nuevo) == (nuevo, None) and nuevo in nuevos
    assert len(seed_dev.RUT_ANTERIORES) == 6


def test_ningun_archivo_de_pruebas_o_demostracion_usa_los_rut_antiguos_invalidos_para_registrar_clientes():
    import seed_dev
    antiguos = [a for a in seed_dev.RUT_ANTERIORES]
    for ruta in ("tests/mysql_desechable.py", "frontend/clientes/registrar_clientes.html", "README.md"):
        texto = open(os.path.join(RAIZ, ruta), encoding="utf-8").read()
        assert not [a for a in antiguos if a in texto] and "12.345.678-9" not in texto, ruta


def test_el_revisor_de_ruts_reporta_sin_modificar():
    sys.path.insert(0, os.path.join(RAIZ, "database"))
    import revisar_ruts
    filas = [(1, "12.345.678-5", "Al día S.A."), (2, "12345678-5", "Mismo RUT, otro formato"), (3, "76.543.210-9", "Dígito malo"),
             (4, "99", "Formato malo"), (5, "12.000.011-K", "Con K"), (6, "12.000.008-k", "Con k minúscula")]
    hallazgos = revisar_ruts.revisar(filas)
    por_cliente = {}
    for id_cliente, _, motivo in hallazgos:
        por_cliente.setdefault(id_cliente, []).append(motivo)
    assert set(por_cliente) == {1, 2, 3, 4, 6}, "el 5 está correcto"
    assert any("varios clientes" in m for m in por_cliente[1]) and any("varios clientes" in m for m in por_cliente[2])
    assert any("normalizado" in m for m in por_cliente[2]) and any("normalizado" in m for m in por_cliente[6])
    assert por_cliente[3] == [MENSAJE_RUT_DIGITO] and por_cliente[4] == [MENSAJE_RUT]
    assert revisar_ruts.revisar([(1, "12.345.678-5", "x"), (2, "11.111.111-1", "y")]) == []


def test_el_formulario_borra_el_mensaje_anterior_antes_de_validar_de_nuevo():
    """Tras corregir el RUT y cancelar la confirmación seguía a la vista el error anterior."""
    js = open(os.path.join(RAIZ, "frontend", "clientes", "registrar_clientes.js"), encoding="utf-8").read()
    assert js.index('mostrarMensaje("");') < js.index("window.Rut.validar(")
