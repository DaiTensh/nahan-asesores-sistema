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
    bloque = css[css.index("@media (max-width: 1100px)"):]
    assert "flex-direction: column" in bloque, "la barra se apila antes de que el título se encime con la fecha"
    assert re.search(r"\.topbar-search\s*\{\s*min-width: 0;\s*flex: 1 1 220px", bloque)


def _fetch_con_json_sin_cuerpo(js):
    """Llamadas fetch(...) que declaran Content-Type JSON pero no envían body."""
    encontrados = []
    for coincidencia in re.finditer(r"fetch\(", js):
        profundidad, i = 1, coincidencia.end()
        while i < len(js) and profundidad:
            profundidad += {"(": 1, ")": -1}.get(js[i], 0)
            i += 1
        bloque = js[coincidencia.start():i]
        if "application/json" in bloque and "body" not in bloque:
            encontrados.append(js[:coincidencia.start()].count("\n") + 1)
    return encontrados


def test_ninguna_solicitud_del_frontend_declara_json_sin_enviar_cuerpo():
    """Detener el temporizador y deshabilitar/eliminar clientes fallaban con 400 por esto."""
    fallos = {}
    for ruta in glob.glob(os.path.join(FRONTEND, "**", "*.js"), recursive=True):
        lineas = _fetch_con_json_sin_cuerpo(leer(ruta))
        if lineas:
            fallos[nombre(ruta)] = lineas
    assert fallos == {}


PAGINAS_SOLO_ADMINISTRADOR = [
    "historial/historial.html", "reportes/reportes.html", "reportes/productividad.html", "reportes/historial_consolidado.html",
    "respaldos/respaldos.html", "usuarios/usuarios.html", "usuarios/modificar_usuario.html", "usuarios/desactivar_usuario.html",
    "usuarios/asignar_rol.html", "usuarios/configuracion_sesion.html", "clientes/eliminar_cliente.html", "clientes/cambiar_estado.html",
]


@pytest.mark.parametrize("pagina", PAGINAS_SOLO_ADMINISTRADOR)
def test_las_pantallas_de_administrador_redirigen_a_quien_no_lo_es(pagina):
    """El backend ya responde 403; la pantalla no debe mostrarse vacía a un usuario operativo."""
    assert 'protegerPagina(["ADMINISTRADOR"])' in leer(os.path.join(FRONTEND, pagina))


def _acciones_que_registra_el_backend():
    codigos = set()
    for ruta in glob.glob(os.path.join(RAIZ, "backend", "**", "*.py"), recursive=True):
        texto = leer(ruta)
        codigos |= set(re.findall(r'registrar_auditoria\(\s*[^,]+,\s*[^,]+,\s*"[a-z_]+",\s*"([A-Z_0-9]+)"', texto))
        codigos |= set(re.findall(r'^ACCION_[A-Z_]+ = "([A-Z_0-9]+)"', texto, re.M))
    return codigos


def test_toda_accion_de_auditoria_tiene_un_nombre_legible():
    """Cada acción nueva debe agregarse a assets/js/etiquetas_auditoria.js; si no, la pantalla muestra el código interno."""
    js = leer(os.path.join(FRONTEND, "assets", "js", "etiquetas_auditoria.js"))
    etiquetadas = set(re.findall(r"^\s{4}([A-Z_0-9]+): \"", js, re.M))
    codigos = _acciones_que_registra_el_backend()
    assert len(codigos) >= 30
    assert codigos - etiquetadas == set()


@pytest.mark.parametrize("pagina,script", [
    ("dashboard/dashboard.html", "cambios_recientes.js"), ("historial/historial.html", "historial.js"),
    ("reportes/historial_consolidado.html", "historial_consolidado.js"),
])
def test_las_pantallas_de_auditoria_usan_los_nombres_legibles(pagina, script):
    html = leer(os.path.join(FRONTEND, pagina))
    assert html.index("etiquetas_auditoria.js") < html.index(script), "el helper se carga antes que el script de la pantalla"
    assert "window.etiquetaAccionAuditoria(" in leer(os.path.join(FRONTEND, pagina.split("/")[0], script))
