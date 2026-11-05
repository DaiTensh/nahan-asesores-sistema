# -*- coding: utf-8 -*-
"""Regresiones de la auditoría de cierre del Incremento 4 que viven en la interfaz.

El código de la interfaz es JavaScript sin framework y estas pruebas corren sin navegador: fijan en el
código fuente lo que se comprobó en Chrome durante la auditoría (menú con scroll, textos y formatos).
Las que dependen del backend (fechas de usuarios y clientes, avisos) están junto a las de su módulo.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

from backend.utils.estados_tarea import etiqueta_estado
from backend.utils.security import LARGO_MINIMO_PASSWORD

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(RAIZ, "frontend")


def leer(*partes):
    with open(os.path.join(FRONTEND, *partes), encoding="utf-8") as archivo:
        return archivo.read()


def test_menu_lateral_tiene_una_zona_con_scroll_propia():
    """Con Administración abierta el menú mide ~1000 px: sin scroll, Tarifas, Respaldos y el cierre de sesión
    quedaban fuera de pantalla en 1366x768 y en 1440x900."""
    js = leer("assets", "js", "navigation.js")
    css = leer("assets", "css", "navigation.css")

    assert 'zonaEnlaces.className = "sidebar-scroll"' in js
    assert "nav.appendChild(zonaEnlaces)" in js
    # Los enlaces y el grupo de administración van dentro de la zona; el pie queda fuera de ella.
    assert "zonaEnlaces.appendChild(detalles)" in js
    bloque = css[css.index(".sidebar-scroll {"):]
    bloque = bloque[:bloque.index("}")]
    assert "overflow-y: auto" in bloque and "min-height: 0" in bloque


def test_historial_del_detalle_de_tarea_usa_etiquetas_legibles():
    html = leer("tareas", "detalle_tarea.html")

    assert html.index("etiquetas_auditoria.js") < html.index("detalle_tarea.js")
    assert "etiquetaAccionAuditoria(evento.accion)" in leer("tareas", "detalle_tarea.js")


def test_dashboard_de_finalizadas_usa_su_propio_texto_vacio_y_dice_el_periodo():
    js = leer("dashboard", "dashboard.js")
    html = leer("dashboard", "dashboard.html")

    assert js.count("Sin tareas finalizadas en el período.") == 3
    assert 'mensajeVacio = "Sin tareas pendientes."' in js
    assert "Finalizadas este mes" in html and "Comparación con el mes anterior" in html


def test_baja_de_cliente_informa_tareas_y_documentos():
    js = leer("clientes", "eliminar_cliente.js")

    assert "${data.tareas_activas} tareas activas y ${data.documentos_activos} documentos vigentes" in js


def test_listado_de_tareas_avisa_cuando_no_se_pudo_cargar():
    js = leer("tareas", "tareas.js")

    assert "function mostrarErrorListado" in js
    assert js.count("mostrarErrorListado(") >= 3  # definición, respuesta con error y excepción de red


def test_eliminar_usuario_no_pide_confirmacion_critica_ni_usa_alert():
    js = leer("usuarios", "desactivar_usuario.js")
    cuerpo = js[js.index("function eliminarUsuario"):]

    assert "confirmarAccion" not in cuerpo and "alert(" not in cuerpo
    assert "mostrarMensaje(" in cuerpo


def test_las_fechas_de_registro_se_formatean_en_las_tres_pantallas():
    for ruta in (("usuarios", "usuarios.js"), ("usuarios", "modificar_usuario.js"), ("clientes", "listar_clientes.js")):
        js = leer(*ruta)
        assert "function formatearFechaRegistro" in js, ruta
        assert "formatearFechaRegistro(" in js.split("function formatearFechaRegistro", 1)[1].split("}\n", 1)[1], ruta


def test_etiquetas_de_estado_de_tarea():
    assert etiqueta_estado("EN_PROCESO") == "En proceso"
    assert etiqueta_estado("EN_REVISION") == "En revisión"
    assert etiqueta_estado("ESTADO_NUEVO") == "ESTADO_NUEVO"


def test_tablas_principales_caben_en_1366_px():
    """Medido en Chrome: Tareas pedía 1048 px (la columna Acciones quedaba cortada) y la carga de trabajo del
    dashboard se pasaba 26 px; la tabla de usuarios se ensanchaba con nombres y correos largos."""
    tareas = leer("tareas", "tareas.css")
    dashboard = leer("dashboard", "dashboard.css")
    usuarios = leer("usuarios", "usuarios.css")

    assert ".tareas-table td" in tareas and "padding-left: 8px" in tareas
    assert ".dashboard-table td" in dashboard and "padding-left: 10px" in dashboard
    assert ".usuarios-tabla td { overflow-wrap: anywhere; }" in usuarios


# H-11 — cargador del dashboard → panel que marca como fallido (clave de PANELES en dashboard.js).
CARGADORES_DEL_DASHBOARD = {
    "cargarResumenUsuarios": "usuarios",
    "cargarCargaTrabajoPorUsuario": "cargaTrabajo",
    "cargarTareasVencidas": "vencidas",
    "cargarResumenTareasPendientes": "pendientes",
    "cargarResumenTareasFinalizadas": "finalizadas",
    "cargarDistribucionPorArea": "distribucion",
    "cargarResumenTareas": "estadoTareas",
    "cargarTareasPrioritarias": "prioritarias",
    "cargarTareasPorVencer": "porVencer",
}


def _cuerpo_de(js, funcion):
    inicio = js.index(f"async function {funcion}(")
    siguiente = re.search(r"\n(?:async )?function ", js[inicio + 1:])
    return js[inicio:inicio + 1 + siguiente.start()] if siguiente else js[inicio:]


@pytest.mark.parametrize("funcion,panel", CARGADORES_DEL_DASHBOARD.items())
def test_dashboard_marca_el_panel_cuando_su_peticion_falla(funcion, panel):
    """Con una respuesta 500 o sin red los contadores quedaban en 0, como si no hubiera datos."""
    cuerpo = _cuerpo_de(leer("dashboard", "dashboard.js"), funcion)

    assert cuerpo.count(f'marcarErrorPanel("{panel}")') == 2  # respuesta con error y excepción de red
    assert cuerpo.count(f'limpiarErrorPanel("{panel}")') == 1  # al llegar datos desaparece el aviso


def test_dashboard_resumen_de_clientes_cae_al_listado_sin_inventar_totales():
    js = leer("dashboard", "dashboard.js")
    resumen = _cuerpo_de(js, "cargarResumenClientes")
    respaldo = _cuerpo_de(js, "cargarClientesDesdeListado")

    assert resumen.count("await cargarClientesDesdeListado()") == 2
    assert 'limpiarErrorPanel("clientes")' in resumen
    # El respaldo trae solo 5 clientes: los muestra en la lista, pero sus contadores quedan en «—» con aviso.
    assert respaldo.count('marcarErrorPanel("clientes")') == 3
    assert "clientes.length" not in respaldo and "clientes.filter" not in respaldo


def test_dashboard_los_paneles_de_error_apuntan_a_elementos_que_existen():
    js = leer("dashboard", "dashboard.js")
    html = leer("dashboard", "dashboard.html")
    paneles = js[js.index("const PANELES = {"):js.index("function marcarErrorPanel")]
    ids = [i for lista in re.findall(r"(?:contadores|listas): \[([^\]]*)\]", paneles)
           for i in re.findall(r'"([^"]+)"', lista)]

    assert len(ids) >= 30
    assert [i for i in ids if f'id="{i}"' not in html] == []
    assert 'aviso.className = "mensaje error"' in js and 'aviso.setAttribute("role", "alert")' in js
    assert '"—"' in js  # el contador muestra un guion, no un 0 que parezca dato real


def test_alta_de_usuario_declara_el_largo_minimo_de_contrasena_del_servidor():
    """H-13: el servidor exige LARGO_MINIMO_PASSWORD caracteres y el formulario solo avisaba después de confirmar."""
    for pantalla in (("usuarios", "usuarios.html"), ("auth", "restablecer.html")):
        campo = re.search(r'<input[^>]*id="password"[^>]*>', leer(*pantalla)).group(0)
        assert f'minlength="{LARGO_MINIMO_PASSWORD}"' in campo, pantalla


def test_detener_temporizador_deja_visible_el_mensaje_de_exito():
    """H-18: cargarContexto() reescribía el aviso («Cargando…» y luego vacío) y el éxito nunca se veía."""
    js = leer("control_horas", "control_horas.js")
    cuerpo = _cuerpo_de(js, "detenerTemporizador")

    assert cuerpo.index("await cargarContexto()") < cuerpo.rindex("mostrarMensaje(textoExito")
    assert cuerpo.count("mostrarMensaje(textoExito") == 2  # al detener y al terminar de recargar
    assert 'mensajeControl.classList.contains("error")' in cuerpo  # no pisa un error de la recarga


# H-20 — un solo formato de fecha y hora (dd-mm-aaaa hh:mm, 24 h) para detalle de tarea, control de horas y avisos.
def _formato_con_node(*casos):
    node = shutil.which("node")
    if node is None:
        pytest.skip("requiere node para ejecutar fechas.js")
    codigo = (
        "global.window = {};"
        f"require({json.dumps(os.path.join(FRONTEND, 'assets', 'js', 'fechas.js'))});"
        f"const casos = {json.dumps(casos)};"
        "console.log(JSON.stringify(casos.map(([v, o]) => window.formatearFechaHora24(v, o))));"
    )
    salida = subprocess.run([node, "-e", codigo], capture_output=True, text=True, timeout=30, check=True).stdout
    return json.loads(salida)


def test_formatearFechaHora24_usa_reloj_de_24_horas_sin_a_m_ni_coma():
    resultado = _formato_con_node(
        ["2026-11-05T13:01:05", {}],                                # hora local sin zona (control de horas)
        ["Thu, 05 Nov 2026 01:25:10 GMT", {"utc": True}],           # hora del servidor rotulada GMT (tareas, avisos)
        ["Thu, 05 Nov 2026 00:05:00 GMT", {"utc": True}],           # medianoche: 00:05, no 24:05 ni 12:05 a. m.
        ["Thu, 05 Nov 2026 23:59:59 GMT", {"utc": True}],
        ["no es una fecha", {}],
    )

    assert resultado == ["05-11-2026 13:01", "05-11-2026 01:25", "05-11-2026 00:05", "05-11-2026 23:59", "no es una fecha"]


def test_las_tres_pantallas_con_hora_usan_el_formateador_unico():
    for archivo in (("tareas", "detalle_tarea.js"), ("control_horas", "control_horas.js"), ("assets", "js", "notificaciones.js")):
        js = leer(*archivo)
        assert "formatearFechaHora24(" in js, archivo
        assert 'toLocaleString("es-CL"' not in js, archivo  # el reloj de 12 h con «a. m.» venía de aquí
    for pagina in (("tareas", "detalle_tarea.html"), ("control_horas", "control_horas.html")):
        html = leer(*pagina)
        assert html.index("fechas.js") < html.index(pagina[1].replace(".html", ".js")), pagina
    # Los avisos del topbar se cargan después de fechas.js, que es la que les da formato.
    assert 'montarModuloTopbar("fechas", () => montarModuloTopbar("notificaciones"))' in leer("assets", "js", "topbar.js")


# H-19 — la acción se llama igual que el requisito RF03: «eliminar o deshabilitar».
def test_baja_de_cliente_usa_el_mismo_vocabulario_en_listado_y_pantalla():
    listado = leer("clientes", "listar_clientes.js")
    pantalla = leer("clientes", "eliminar_cliente.html")

    assert 'crearEnlaceAccion("Eliminar", `eliminar_cliente.html' in listado and '"Quitar"' not in listado
    assert "<title>Eliminar o deshabilitar cliente</title>" in pantalla and "<h1>Eliminar o deshabilitar cliente</h1>" in pantalla
    # Los botones nombran el resultado concreto según los vínculos del cliente.
    botones = leer("clientes", "eliminar_cliente.js")
    assert '"Deshabilitar cliente"' in botones and '"Eliminar definitivamente"' in botones


# H-10 y coherencia visual — los avisos usan el cuadro de la aplicación, no el alert() nativo del navegador.
def test_la_interfaz_no_usa_alert_nativo_salvo_el_respaldo_de_permissions():
    encontrados = []
    for carpeta, _, archivos in os.walk(FRONTEND):
        for nombre in archivos:
            if nombre.endswith(".js"):
                ruta = os.path.join(carpeta, nombre)
                with open(ruta, encoding="utf-8") as archivo:
                    for numero, linea in enumerate(archivo, 1):
                        if not linea.lstrip().startswith("//") and re.search(r"(?<![\w.])alert\(", linea):
                            encontrados.append((os.path.relpath(ruta, FRONTEND), linea.strip()))

    assert encontrados == [(os.path.join("assets", "js", "permissions.js"), "alert(aviso);")]


def test_avisarAccion_tiene_el_aspecto_de_las_confirmaciones_y_se_cierra_con_esc():
    js = leer("assets", "js", "confirmar.js")
    cuerpo = js[js.index("window.avisarAccion"):]

    assert 'cuadro.setAttribute("role", "alertdialog")' in cuerpo and 'cuadro.setAttribute("aria-modal", "true")' in cuerpo
    assert 'evento.key === "Escape"' in cuerpo and "return new Promise" in cuerpo
    for tipo in ("error:", "advertencia:", "exito:", "info:"):
        assert tipo in js[js.index("const AVISOS"):js.index("window.avisarAccion")]


def test_acceso_denegado_espera_el_aviso_antes_de_redirigir():
    assert "await avisarAccion(aviso, \"advertencia\")" in leer("assets", "js", "permissions.js")
    horas = leer("control_horas", "control_horas.js")
    cuerpo = _cuerpo_de(horas.replace("async function manejarAccesoDenegado", "async function manejarAccesoDenegado"), "manejarAccesoDenegado")
    assert cuerpo.index("await avisarAccion(") < cuerpo.index('window.location.href = "../auth/login.html"')


# H-16 — el login no atribuye a la inactividad una sesión que terminó por otra causa.
def test_login_distingue_cierre_por_inactividad_de_sesion_finalizada():
    login = leer("auth", "login.js")
    inactividad = leer("assets", "js", "inactividad.js")

    assert "Tu sesión se cerró por inactividad." in login and "Tu sesión ya no está activa." in login
    assert "sesion:" in login
    assert inactividad.count("irAlLogin(motivoDeCierre())") == 2  # respuesta 401 al renovar y al consultar
    assert "ultimaLectura" in inactividad and "function motivoDeCierre" in inactividad
    # El cierre por cuenta regresiva (RF59) conserva el aviso de inactividad.
    assert re.search(r"cerrarPorInactividad\(\) \{.*?irAlLogin\(\);", inactividad, re.S)


# H-17 — enlace «Saltar al contenido» para quien navega con el teclado.
def test_hay_enlace_para_saltar_al_contenido_en_todas_las_pantallas_con_menu():
    js = leer("assets", "js", "navigation.js")
    css = leer("assets", "css", "navigation.css")

    assert js.index("agregarSaltoAlContenido();") > js.index("async function cargarNavegacion")
    assert 'enlace.href = `#${principal.id}`' in js and "document.body.prepend(enlace)" in js
    bloque = css[css.index(".saltar-contenido {"):]
    assert "translateY(-200%)" in bloque[:bloque.index("}")]          # fuera de pantalla hasta recibir el foco
    assert ".saltar-contenido:focus {\n  transform: translateY(0);" in css
    # El destino existe: toda pantalla con menú tiene un <main>.
    for carpeta in ("auth", "clientes", "control_horas", "dashboard", "historial", "reportes", "respaldos", "tareas", "tarifas", "usuarios"):
        for archivo in sorted(os.listdir(os.path.join(FRONTEND, carpeta))):
            if archivo.endswith(".html") and "navigation.js" in leer(carpeta, archivo):
                assert "<main" in leer(carpeta, archivo), (carpeta, archivo)


# H-16 y RF59 — comportamiento real de inactividad.js ante un 401, con reloj y fetch simulados (node).
ARNES_INACTIVIDAD = r"""
const fs = require('fs'), vm = require('vm');
const codigo = fs.readFileSync(RUTA, 'utf8');
const universal = () => new Proxy(function () {}, {
  get: (_, p) => (p === Symbol.toPrimitive ? () => '' : universal()),
  apply: () => universal(), set: () => true, construct: () => universal(),
});
const tick = () => new Promise(r => setImmediate(r));
async function escenario([respuestas, avance]) {
  let ahora = 1000000;
  const intervalos = [];
  const ventana = { location: { href: '' }, API_CONFIG: { API_URL: 'http://api', credentials: 'include' }, addEventListener() {} };
  const contexto = {
    window: ventana, document: universal(), console,
    fetch: async () => { const r = respuestas.shift(); return { status: r.status, ok: r.status < 400, json: async () => r.cuerpo }; },
    setInterval: fn => { intervalos.push(fn); return 1; }, clearInterval() {}, setTimeout: () => 1, clearTimeout() {},
    Date: { now: () => ahora },
  };
  vm.createContext(contexto);
  vm.runInContext(codigo, contexto);
  await tick();                       // primera lectura al cargar la pantalla
  ahora += avance * 1000;
  await intervalos[0]();              // siguiente consulta periódica
  await tick();
  return ventana.location.href;
}
(async () => { console.log(JSON.stringify(await Promise.all(ESCENARIOS.map(escenario)))); })();
"""


def test_inactividad_solo_atribuye_a_la_inactividad_el_401_que_llega_con_poco_tiempo_restante():
    node = shutil.which("node")
    if node is None:
        pytest.skip("requiere node para ejecutar inactividad.js")
    ok = {"status": 200, "cuerpo": {"segundos_restantes": 280, "aviso_segundos": 15}}
    casi = {"status": 200, "cuerpo": {"segundos_restantes": 40, "aviso_segundos": 15}}
    sin_sesion = {"status": 401, "cuerpo": {}}
    escenarios = [
        [[ok, sin_sesion], 15],       # quedaban 280 s y la sesión ya no existe: otra causa
        [[casi, sin_sesion], 25],     # quedaban 40 s, pasaron 25: se agotó por inactividad
        [[ok, sin_sesion], 400],      # el equipo estuvo suspendido más que el límite: inactividad
        [[sin_sesion], 0],            # primera lectura ya sin sesión: no se atribuye a la inactividad
    ]
    codigo = (f"const RUTA = {json.dumps(os.path.join(FRONTEND, 'assets', 'js', 'inactividad.js'))};"
              f"const ESCENARIOS = {json.dumps(escenarios)};" + ARNES_INACTIVIDAD)
    salida = subprocess.run([node, "-e", codigo], capture_output=True, text=True, timeout=60, check=True).stdout

    assert [url.split("motivo=")[1] for url in json.loads(salida)] == ["sesion", "inactividad", "inactividad", "sesion"]
