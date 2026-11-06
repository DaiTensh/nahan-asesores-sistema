import json
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


def leer(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as archivo:
        return archivo.read()


def extraer_array(js, nombre):
    inicio = js.index(f"const {nombre} = [")
    fin = js.index("\n];", inicio) + 3
    return js[inicio:fin]


@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
def test_panel_alta_abre_cierra_mueve_el_foco_y_ignora_ids_inexistentes():
    ruta = os.path.join(RAIZ, "frontend", "assets", "js", "panel_alta.js")
    guion = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const elementos = new Map();
const eventosOrden = [];
function crearElemento() {
  return {
    hidden: false,
    atributos: {},
    eventos: {},
    foco: 0,
    eventosOrden,
    desplazamientos: [],
    setAttribute(nombre, valor) { this.atributos[nombre] = valor; },
    getAttribute(nombre) { return this.atributos[nombre] || null; },
    addEventListener(nombre, callback) { this.eventos[nombre] = callback; },
    focus(opciones) { this.foco += 1; this.ultimoFoco = opciones; this.eventosOrden.push('focus'); },
    scrollIntoView(opciones) { this.desplazamientos.push(opciones); this.eventosOrden.push('scroll'); }
  };
}
for (const id of ['boton', 'panel', 'campo', 'cerrar']) elementos.set(id, crearElemento());
const contexto = { document: { getElementById: id => elementos.get(id) || null } };
vm.createContext(contexto);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), contexto);
const boton = elementos.get('boton'), panel = elementos.get('panel');
const campo = elementos.get('campo'), cerrar = elementos.get('cerrar');
const api = contexto.configurarPanelAlta({
  botonId: 'boton', panelId: 'panel', primerCampoId: 'campo', botonCerrarId: 'cerrar'
});
assert.strictEqual(panel.hidden, true);
assert.strictEqual(boton.atributos['aria-expanded'], 'false');
assert.strictEqual(boton.atributos['aria-controls'], 'panel');
boton.eventos.click();
assert.strictEqual(panel.hidden, false);
assert.strictEqual(boton.atributos['aria-expanded'], 'true');
assert.strictEqual(campo.foco, 1);
assert.strictEqual(JSON.stringify(campo.ultimoFoco), '{"preventScroll":true}');
assert.strictEqual(JSON.stringify(panel.desplazamientos), '[{"block":"nearest"}]');
assert.deepStrictEqual(panel.eventosOrden, ['focus', 'scroll']);
boton.eventos.click();
assert.strictEqual(panel.hidden, true);
assert.strictEqual(boton.atributos['aria-expanded'], 'false');
assert.strictEqual(boton.foco, 1);
api.abrir();
cerrar.eventos.click();
assert.strictEqual(panel.hidden, true);
assert.strictEqual(boton.foco, 2);
assert.strictEqual(api.estaAbierto(), false);
assert.strictEqual(contexto.configurarPanelAlta({ botonId: 'ausente', panelId: 'panel' }), null);
console.log('ok');
"""
    resultado = subprocess.run(
        [NODE, "-e", guion, ruta], capture_output=True, text=True, timeout=30
    )

    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "ok"


def test_paneles_de_alta_reservan_espacio_para_la_barra_superior():
    for ruta, selector in (
        (("frontend", "tareas", "tareas.css"), "#panelNuevaTarea"),
        (("frontend", "usuarios", "usuarios.css"), "#panelNuevoUsuario")
    ):
        css = leer(*ruta)
        regla = re.search(
            rf"{re.escape(selector)}\s*\{{\s*scroll-margin-top:\s*(\d+)px;\s*\}}",
            css
        )
        assert regla and int(regla.group(1)) >= 152, ruta


def test_datos_de_usuario_permiten_dividir_correos_largos_en_movil():
    for pantalla in ("asignar_rol", "desactivar_usuario"):
        css = leer("frontend", "usuarios", f"{pantalla}.css")
        regla = re.search(r"\.datos p\s*\{([^}]*)\}", css, re.S)
        assert regla and re.search(r"overflow-wrap:\s*anywhere\s*;", regla.group(1)), pantalla


def test_menu_conserva_los_items_base_y_solo_las_seis_entradas_administrativas():
    js = leer("frontend", "assets", "js", "navigation.js")
    nav_items = extraer_array(js, "NAV_ITEMS")
    admin_items = extraer_array(js, "ADMIN_ITEMS")
    ids_nav = re.findall(r'id: "([^"]+)"', nav_items)
    ids_admin = re.findall(r'id: "([^"]+)"', admin_items)
    hrefs = re.findall(r'href: "([^"]+)"', nav_items + admin_items)

    assert ids_nav == ["dashboard", "clientes", "tareas", "control-horas"]
    assert ids_admin == [
        "reportes", "historial", "usuarios", "configuracion-sesion", "tarifas", "respaldos"
    ]
    assert not {"productividad", "historial-consolidado", "modificar", "desactivar", "rol"} & set(ids_admin)
    for href in hrefs:
        destino = os.path.normpath(os.path.join(RAIZ, "frontend", "auth", href))
        assert os.path.isfile(destino), href


def test_paginas_retiradas_del_menu_siguen_protegidas_y_resaltan_su_modulo():
    paginas = [
        ("frontend/usuarios/modificar_usuario.html", "usuarios"),
        ("frontend/usuarios/asignar_rol.html", "usuarios"),
        ("frontend/usuarios/desactivar_usuario.html", "usuarios"),
        ("frontend/reportes/productividad.html", "reportes"),
        ("frontend/reportes/historial_consolidado.html", "reportes")
    ]
    for ruta, modulo in paginas:
        assert os.path.isfile(os.path.join(RAIZ, ruta))
        html = leer(*ruta.split("/"))
        assert 'protegerPagina(["ADMINISTRADOR"])' in html, ruta
        assert f'cargarNavegacion("{modulo}")' in html, ruta


def test_usuarios_reutiliza_el_panel_y_ofrece_acciones_por_fila_con_refresco():
    html = leer("frontend", "usuarios", "usuarios.html")
    js = leer("frontend", "usuarios", "usuarios.js")
    panel = re.search(r'<section[^>]*id="panelNuevoUsuario"[^>]*hidden[^>]*>', html)
    assert panel
    assert html.index('id="panelNuevoUsuario"') < html.index('class="usuarios-listado"')
    assert 'id="btnNuevoUsuario"' in html and 'id="btnCerrarNuevoUsuario"' in html
    for campo in ("formUsuario", "nombres", "email", "id_rol", "id_area", "password", "mensaje"):
        assert f'id="{campo}"' in html
    assert 'id="password" class="form-input" minlength="8" required' in html
    assert html.index("../assets/js/panel_alta.js") < html.index("./usuarios.js")

    assert 'modificar_usuario.html?id=${id}' in js
    assert 'asignar_rol.html?id=${id}' in js
    assert 'desactivar_usuario.html?id=${id}' in js
    assert 'if (usuario.estado === "ACTIVO")' in js
    assert "Ver perfil" not in html + js
    for etiqueta in ("Editar a ${usuario.nombres}", "Asignar rol a ${usuario.nombres}",
                     "Deshabilitar a ${usuario.nombres}"):
        assert etiqueta in js

    manejador = re.search(
        r'formUsuario\.addEventListener\("submit", async \(event\) => \{(?P<cuerpo>.*?)\n\}\);',
        js, re.S
    ).group("cuerpo")
    assert "if (!response.ok)" in manejador
    exito = manejador.index('mensaje.className = "mensaje success"')
    assert manejador.index("formUsuario.reset()", exito) > exito
    assert manejador.index("sincronizarAreaConRol()", exito) > exito
    assert manejador.index("await cargarListadoUsuarios()", exito) > exito


def test_asignar_rol_y_deshabilitar_aceptan_id_numerico_en_la_url():
    for pantalla in ("asignar_rol", "desactivar_usuario"):
        js = leer("frontend", "usuarios", f"{pantalla}.js")
        assert 'new URLSearchParams(window.location.search).get("id")' in js
        assert r"/^\d+$/.test(idUsuario)" in js
        assert "Number(idUsuario) > 0" in js
        assert "cargarUsuarioPorId(idUsuario)" in js


def test_deshabilitar_no_ofrece_eliminacion_y_conserva_la_confirmacion_critica():
    html = leer("frontend", "usuarios", "desactivar_usuario.html")
    js = leer("frontend", "usuarios", "desactivar_usuario.js")
    assert "eliminarUsuario" not in html + js
    assert "Eliminar Usuario" not in html + js
    assert "Eliminar o deshabilitar" not in html
    assert "alert(" not in js
    cuerpo = js[js.index("async function desactivarUsuario"): ]
    assert 'confirmarAccion("¿Está seguro de deshabilitar este usuario?", "critica")' in cuerpo
    assert '`${API_URL}/usuarios/${usuarioActual.id_usuario}/desactivar`' in cuerpo
    assert 'method: "PUT"' in cuerpo
    assert "Content-Type" not in cuerpo and "body:" not in cuerpo
    assert 'href="usuarios.html" class="btn btn-secondary">Volver a Usuarios</a>' in html


def test_tres_informes_comparten_navegacion_y_marcan_solo_la_pagina_actual():
    destinos = ["reportes.html", "productividad.html", "historial_consolidado.html"]
    paginas = [
        ("reportes", "reportes.html"),
        ("productividad", "productividad.html"),
        ("historial_consolidado", "historial_consolidado.html")
    ]
    for pantalla, actual in paginas:
        html = leer("frontend", "reportes", f"{pantalla}.html")
        nav = re.search(
            r'<nav class="reportes-header-actions" aria-label="Informes">(.*?)</nav>',
            html, re.S
        ).group(1)
        enlaces = re.findall(r'<a\b([^>]*)>', nav)
        destinos_enlaces = [re.search(r'href="([^"]+)"', atributos).group(1) for atributos in enlaces]
        assert destinos_enlaces == destinos
        actuales = [
            re.search(r'href="([^"]+)"', atributos).group(1)
            for atributos in enlaces if 'aria-current="page"' in atributos
        ]
        assert actuales == [actual]
        assert nav.count('aria-current="page"') == 1


def test_tarifas_se_inserta_solo_para_administradores_en_control_de_horas():
    html = leer("frontend", "control_horas", "control_horas.html")
    js = leer("frontend", "control_horas", "control_horas.js")
    assert 'id="accionesControlHoras" hidden' in html
    assert '../tarifas/tarifas.html' not in html and ">Tarifas</a>" not in html
    bloque = re.search(
        r'if \(usuarioActual\.nombre_rol === "ADMINISTRADOR"\) \{(.*?)\n  \}',
        js, re.S
    ).group(1)
    assert 'enlaceTarifas.href = "../tarifas/tarifas.html"' in bloque
    assert 'enlaceTarifas.textContent = "Tarifas"' in bloque
    assert "accionesControlHoras.appendChild(enlaceTarifas)" in bloque
    assert "accionesControlHoras.hidden = false" in bloque


def test_tareas_abre_el_formulario_existente_desde_el_encabezado():
    html = leer("frontend", "tareas", "tareas.html")
    js = leer("frontend", "tareas", "tareas.js")
    encabezado = html[html.index('<section class="tareas-header">'):].split("</section>", 1)[0]
    panel = re.search(
        r'<section class="tareas-section" id="panelNuevaTarea" hidden>(.*?)</section>',
        html, re.S
    ).group(1)
    assert 'id="btnNuevaTarea"' in encabezado and "Nueva tarea" in encabezado
    assert 'id="formTarea"' in panel
    assert html.index("../assets/js/panel_alta.js") < html.index("./tareas.js")
    for campo in (
        "formTarea", "cliente_busqueda", "id_cliente", "id_area", "responsable_busqueda",
        "id_responsable", "prioridad", "fecha_inicio", "fecha_vencimiento", "titulo",
        "descripcion", "mensajeTarea"
    ):
        assert f'id="{campo}"' in html
    assert "Crear Tarea" not in html.replace(panel, "")
    assert 'botonId: "btnNuevaTarea"' in js
    assert 'panelId: "panelNuevaTarea"' in js
    assert 'primerCampoId: "cliente_busqueda"' in js


def test_codigo_nuevo_no_inserta_html_dinamico_ni_evalua_codigo():
    archivos = [
        ("frontend", "assets", "js", "panel_alta.js"),
        ("frontend", "usuarios", "usuarios.js"),
        ("frontend", "usuarios", "asignar_rol.js"),
        ("frontend", "usuarios", "desactivar_usuario.js"),
        ("frontend", "control_horas", "control_horas.js"),
        ("frontend", "tareas", "tareas.js")
    ]
    prohibidos = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(")
    for ruta in archivos:
        codigo = leer(*ruta)
        assert not any(token in codigo for token in prohibidos), ruta
