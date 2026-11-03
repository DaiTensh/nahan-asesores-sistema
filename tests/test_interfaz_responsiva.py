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
    "respaldos/respaldos.html", "tarifas/tarifas.html", "usuarios/usuarios.html", "usuarios/modificar_usuario.html", "usuarios/desactivar_usuario.html",
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
    ("reportes/historial_consolidado.html", "historial_consolidado.js"), ("clientes/ficha_cliente.html", "ficha_cliente.js"),
])
def test_las_pantallas_de_auditoria_usan_los_nombres_legibles(pagina, script):
    html = leer(os.path.join(FRONTEND, pagina))
    assert html.index("etiquetas_auditoria.js") < html.index(script), "el helper se carga antes que el script de la pantalla"
    assert "window.etiquetaAccionAuditoria(" in leer(os.path.join(FRONTEND, pagina.split("/")[0], script))


def test_la_pantalla_de_tarifas_no_inserta_html_y_no_declara_json_sin_cuerpo():
    js = leer(os.path.join(FRONTEND, "tarifas", "tarifas.js"))
    for prohibido in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "document.write"):
        assert prohibido not in js
    assert 'pedir(`/tarifas/areas/${area.id_area}`, { method: "DELETE" })' in js
    assert 'id: "tarifas"' in leer(os.path.join(FRONTEND, "assets", "js", "navigation.js"))


def test_la_ficha_del_cliente_no_repite_el_mapa_de_etiquetas_de_auditoria():
    """Un mapa propio en la ficha dejaba sin nombre legible a cualquier acción nueva."""
    js = leer(os.path.join(FRONTEND, "clientes", "ficha_cliente.js"))
    assert "ETIQUETAS_ACCION_HISTORIAL" not in js and "Cliente creado" not in js


def test_toda_pregunta_de_confirmacion_abre_con_signo_de_interrogacion():
    """El español escribe «¿Desea…?»: nueve confirmaciones llevaban solo el cierre."""
    fallos = []
    for ruta in glob.glob(os.path.join(FRONTEND, "**", "*.js"), recursive=True):
        texto = leer(ruta)
        for coincidencia in re.finditer(r"confirm\(\s*([`\"'])((?:\\.|(?!\1).)*)\1", texto, re.S):
            mensaje = coincidencia.group(2)
            if "?" in mensaje and "¿" not in mensaje:
                fallos.append(f"{nombre(ruta)}: {mensaje[:60]}")
    assert fallos == []


def test_la_ficha_del_cliente_cabe_en_360_px():
    """A 360 px las tarjetas del resumen medían 232 px dentro de un contenedor de 178 y la paginación del
    historial ensanchaba toda la sección: con `1fr` a secas la columna no baja del ancho de su contenido."""
    css = leer(os.path.join(FRONTEND, "clientes", "clientes.css"))
    bloque = css[css.index("@media (max-width: 900px)"):css.index("@media (max-width: 480px)")]
    regla = bloque[bloque.index(".clientes-cards,"):]
    assert "grid-template-columns: minmax(0, 1fr);" in regla[:regla.index("}")]
    pagination = css[css.index(".pagination {"):css.index("}", css.index(".pagination {"))]
    assert "flex-wrap: wrap" in pagination


@pytest.mark.parametrize("ruta", ["respaldos/respaldos.js", "dashboard/dashboard.js"])
def test_los_decimales_visibles_usan_coma(ruta):
    """`toFixed` escribe «7.2 KB»; en español de Chile corresponde «7,2 KB» (toLocaleString("es-CL")). Los atributos
    numéricos de ARIA (aria-valuenow) sí llevan punto y no van dentro de una plantilla de texto."""
    js = leer(os.path.join(FRONTEND, ruta))
    assert re.findall(r"\$\{[^}]*toFixed\(", js) == []
    assert 'toLocaleString("es-CL"' in js


def test_las_etiquetas_de_accesibilidad_llevan_tilde():
    """Un lector de pantalla pronuncia mal «Seleccion»; el corrector del sistema lo marcaba."""
    assert 'aria-label="Selección de tarea"' in leer(os.path.join(FRONTEND, "control_horas", "control_horas.html"))


def test_la_fecha_de_inicio_de_rf14_esta_en_el_alta_la_edicion_y_el_detalle():
    """RF14 pide fecha de inicio y fecha límite al crear una tarea; se puede corregir y se muestra."""
    for pagina in ("tareas/tareas.html", "tareas/editar_tarea.html"):
        assert 'id="fecha_inicio"' in leer(os.path.join(FRONTEND, pagina)), pagina
    assert 'id="detalleFechaInicio"' in leer(os.path.join(FRONTEND, "tareas", "detalle_tarea.html"))
    for script in ("tareas.js", "editar_tarea.js"):
        js = leer(os.path.join(FRONTEND, "tareas", script))
        assert "fecha_inicio: fechaInicio" in js and "fechaInicio > fechaVencimiento" in js, script
    assert "detalleFechaInicio" in leer(os.path.join(FRONTEND, "tareas", "detalle_tarea.js"))
