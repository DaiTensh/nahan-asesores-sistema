"""Reglas de interfaz que ya fallaron una vez y no deben volver a hacerlo.

Son comprobaciones estáticas sobre los HTML/JS/CSS del frontend (no hay un
navegador en la suite). Cada una corresponde a un defecto confirmado al abrir
la aplicación en un navegador real: ver docs/incremento4/CIERRE_PROGRAMACION_PARA_CHATGPT.md.
"""
import glob
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(RAIZ, "frontend")
PAGINAS = sorted(glob.glob(os.path.join(FRONTEND, "*", "*.html")))
PAGINAS_CON_TABLA = [p for p in PAGINAS if "<table" in open(p, encoding="utf-8").read()]


def leer(ruta):
    with open(ruta, encoding="utf-8") as archivo:
        return archivo.read()


def nombre(ruta):
    return os.path.relpath(ruta, FRONTEND)


def test_hay_paginas_que_comprobar():
    assert len(PAGINAS) >= 25


@pytest.mark.parametrize("ruta", PAGINAS, ids=nombre)
def test_toda_pagina_declara_el_viewport(ruta):
    """Sin <meta name="viewport"> un teléfono usa un ancho de 980 px y el CSS responsivo no se aplica."""
    assert re.search(r'<meta name="viewport" content="width=device-width, initial-scale=1">', leer(ruta))


@pytest.mark.parametrize("ruta", PAGINAS, ids=nombre)
def test_toda_pagina_tiene_idioma_y_titulo(ruta):
    html = leer(ruta)
    assert '<html lang="es">' in html
    assert re.search(r"<title>[^<]+</title>", html)


@pytest.mark.parametrize("ruta", [p for p in PAGINAS if "/auth/" not in p], ids=nombre)
def test_cada_pagina_tiene_un_unico_h1(ruta):
    html = leer(ruta)
    assert len(re.findall(r"<h1[\s>]", html)) == 1, "un solo título principal por pantalla"


def test_la_barra_superior_no_repite_el_h1():
    js = leer(os.path.join(FRONTEND, "assets", "js", "topbar.js"))
    assert 'createElement("h1")' not in js and "createElement('h1')" not in js


@pytest.mark.parametrize("ruta", PAGINAS_CON_TABLA, ids=nombre)
def test_las_tablas_se_desplazan_dentro_de_un_contenedor_responsivo(ruta):
    html = leer(ruta)
    tablas = list(re.finditer(r"<table\b", html))
    assert "assets/css/tables.css" in html, "tables.css define .table-responsive"
    for tabla in tablas:
        antes = html[max(0, tabla.start() - 300):tabla.start()]
        assert re.search(r'class="[^"]*table-responsive[^"]*"[^>]*>\s*$', antes), \
            f"{nombre(ruta)}: una tabla no está dentro de .table-responsive"


def test_los_controles_de_la_tabla_de_tareas_tienen_nombre_accesible():
    js = leer(os.path.join(FRONTEND, "tareas", "tareas.js"))
    html = leer(os.path.join(FRONTEND, "tareas", "tareas.html"))
    for fragmento in ('checkbox.setAttribute("aria-label"', 'responsable.setAttribute("aria-label"',
                      'selectorEstado.setAttribute("aria-label"', 'selectorPrioridad.setAttribute("aria-label"',
                      'input.setAttribute("aria-label"'):
        assert fragmento in js, fragmento
    assert 'id="seleccionarTodas" aria-label=' in html
    assert re.search(r'id="redistribuir_destino_busqueda"[^>]*aria-label=', html)


def test_el_menu_arranca_contraido_en_pantallas_estrechas_si_no_hay_preferencia():
    js = leer(os.path.join(FRONTEND, "assets", "js", "navigation.js"))
    assert 'preferenciaSidebar === null' in js and "matchMedia(\"(max-width: 900px)\")" in js


def test_la_fecha_de_la_barra_superior_solo_capitaliza_la_primera_letra():
    css = leer(os.path.join(FRONTEND, "assets", "css", "topbar.css"))
    js = leer(os.path.join(FRONTEND, "assets", "js", "topbar.js"))
    bloque = css[css.index(".topbar-date"):css.index("}", css.index(".topbar-date"))]
    assert "capitalize" not in bloque
    assert "charAt(0).toUpperCase()" in js


def test_la_barra_superior_cabe_en_1024_px():
    css = leer(os.path.join(FRONTEND, "assets", "css", "topbar.css"))
    assert re.search(r"@media \(max-width: 1100px\)\s*\{\s*\.topbar-search\s*\{\s*min-width: 180px", css)
