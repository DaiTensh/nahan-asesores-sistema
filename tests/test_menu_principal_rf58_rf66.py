"""RF58 (navegar por módulos) y RF66 (menú principal siempre visible): comprobación estática del frontend.

No sustituye un recorrido en navegador; verifica los invariantes que, de romperse, dejarían la
navegación inutilizable: cada enlace del menú apunta a una página que existe, las opciones
administrativas solo se pintan para el administrador y todas las pantallas autenticadas cargan el menú.
"""
import glob
import json
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAV = os.path.join(RAIZ, "frontend", "assets", "js", "navigation.js")


def _items(nombre):
    codigo = open(NAV, encoding="utf-8").read()
    m = re.search(r"const %s = (\[.*?\n\]);" % nombre, codigo, re.S)
    assert m, nombre
    if not shutil.which("node"):
        pytest.skip("Node no disponible")
    salida = subprocess.run(["node", "-e", f"console.log(JSON.stringify({m.group(1)}))"],
                            capture_output=True, text=True, check=True).stdout
    return json.loads(salida)


@pytest.mark.parametrize("nombre,minimo", [("NAV_ITEMS", 4), ("ADMIN_ITEMS", 6)])
def test_cada_enlace_del_menu_apunta_a_una_pagina_existente(nombre, minimo):
    items = _items(nombre)
    assert len(items) >= minimo
    for item in items:
        destino = os.path.normpath(os.path.join(RAIZ, "frontend", "dashboard", item["href"]))
        assert os.path.isfile(destino), item["href"]


def test_las_opciones_administrativas_solo_se_pintan_para_el_administrador():
    codigo = open(NAV, encoding="utf-8").read()
    assert 'usuario.nombre_rol === "ADMINISTRADOR"' in codigo
    inicio = codigo.index("if (esAdmin)")
    # El único punto donde se recorren las opciones administrativas está dentro de ese bloque.
    usos = [m.start() for m in re.finditer(r"ADMIN_ITEMS\.forEach", codigo)]
    assert usos and all(u > inicio for u in usos)


def test_todas_las_pantallas_autenticadas_cargan_el_menu():
    sin_menu = [
        p for p in glob.glob(os.path.join(RAIZ, "frontend", "*", "*.html"))
        if "/auth/" not in p and "navigation.js" not in open(p, encoding="utf-8").read()
    ]
    assert sin_menu == []
