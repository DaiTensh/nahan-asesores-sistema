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
let aperturas = 0;
function crearElemento() {
  return {
    hidden: false,
    atributos: {},
    eventos: {},
    cantidadesEvento: {},
    foco: 0,
    eventosOrden,
    desplazamientos: [],
    setAttribute(nombre, valor) { this.atributos[nombre] = valor; },
    getAttribute(nombre) { return this.atributos[nombre] || null; },
    addEventListener(nombre, callback) {
      this.cantidadesEvento[nombre] = (this.cantidadesEvento[nombre] || 0) + 1;
      this.eventos[nombre] = callback;
    },
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
const opcionesPanel = {
  botonId: 'boton', panelId: 'panel', primerCampoId: 'campo', botonCerrarId: 'cerrar',
  alAbrir: () => { aperturas += 1; }
};
const api = contexto.configurarPanelAlta(opcionesPanel);
const apiDuplicada = contexto.configurarPanelAlta(opcionesPanel);
assert.strictEqual(apiDuplicada, api);
assert.strictEqual(boton.cantidadesEvento.click, 1);
assert.strictEqual(cerrar.cantidadesEvento.click, 1);
assert.strictEqual(panel.hidden, true);
assert.strictEqual(boton.atributos['aria-expanded'], 'false');
assert.strictEqual(boton.atributos['aria-controls'], 'panel');
boton.eventos.click();
assert.strictEqual(panel.hidden, false);
assert.strictEqual(boton.atributos['aria-expanded'], 'true');
assert.strictEqual(campo.foco, 1);
assert.strictEqual(aperturas, 1);
assert.strictEqual(JSON.stringify(campo.ultimoFoco), '{"preventScroll":true}');
assert.strictEqual(JSON.stringify(panel.desplazamientos), '[{"block":"nearest"}]');
assert.deepStrictEqual(panel.eventosOrden, ['focus', 'scroll']);
boton.eventos.click();
assert.strictEqual(panel.hidden, true);
assert.strictEqual(boton.atributos['aria-expanded'], 'false');
assert.strictEqual(boton.foco, 1);
assert.strictEqual(JSON.stringify(boton.ultimoFoco), '{"preventScroll":true}');
assert.strictEqual(JSON.stringify(boton.desplazamientos), '[{"block":"nearest"}]');
assert.deepStrictEqual(boton.eventosOrden.slice(-2), ['focus', 'scroll']);
api.abrir();
assert.strictEqual(aperturas, 2);
cerrar.eventos.click();
assert.strictEqual(panel.hidden, true);
assert.strictEqual(boton.foco, 2);
assert.strictEqual(JSON.stringify(boton.desplazamientos), '[{"block":"nearest"},{"block":"nearest"}]');
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
    for ruta, selectores in (
        (("frontend", "tareas", "tareas.css"), ("#panelNuevaTarea", "#btnNuevaTarea")),
        (("frontend", "usuarios", "usuarios.css"), ("#panelNuevoUsuario", "#btnNuevoUsuario"))
    ):
        css = leer(*ruta)
        for selector in selectores:
            assert css.count(selector) == 1, (ruta, selector)
            regla = re.search(
                rf"{re.escape(selector)}\s*\{{\s*scroll-margin-top:\s*(\d+)px;\s*\}}",
                css
            )
            assert regla and int(regla.group(1)) >= 152, (ruta, selector)


@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
def test_listado_espera_el_rol_antes_de_renderizar_acciones_administrativas():
    ruta = os.path.join(RAIZ, "frontend", "usuarios", "usuarios.js")
    guion = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.options = [];
    this.value = '';
    this.classList = { add() {} };
  }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this.options = children; }
  add(child) { this.children.push(child); this.options = this.children; }
  addEventListener() {}
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name] || null; }
  querySelector() { return new Element('button'); }
}
const ids = ['formUsuario','mensaje','id_rol','id_area','tablaUsuarios',
  'mensajeListadoUsuarios','filtroRol','filtroArea','filtroEstado','ordenUsuarios'];
const elementos = Object.fromEntries(ids.map(id => [id, new Element(
  id.startsWith('filtro') || id === 'ordenUsuarios' || id.startsWith('id_') ? 'select' : 'div'
)]));
elementos.formUsuario = new Element('form');
let alCargarDOM;
const contexto = {
  window: { API_CONFIG: { API_URL: 'http://local', credentials: 'include' } },
  document: {
    getElementById: id => elementos[id] || null,
    createElement: tag => new Element(tag),
    addEventListener: (evento, callback) => { if (evento === 'DOMContentLoaded') alCargarDOM = callback; }
  },
  configurarPanelAlta() {},
  obtenerUsuarioActual: async () => ({ nombre_rol: 'ADMINISTRADOR' }),
  nombreRolNatural: value => value,
  fetch: async () => ({
    ok: true,
    json: async () => [{
      id_usuario: 9, nombres: 'Administradora Prueba', email: 'admin@example.invalid',
      nombre_rol: 'ADMINISTRADOR', nombre_area: 'Administración',
      estado: 'ACTIVO', fecha_creacion: '2026-11-06 10:30:00'
    }]
  }),
  URLSearchParams,
  Option: function(text, value) { this.text = text; this.value = value; }
};
vm.createContext(contexto);
let codigo = fs.readFileSync(process.argv[1], 'utf8');
if (process.argv[2] === 'sin-await') {
  codigo = codigo.replace(
    'usuarioActual = await obtenerUsuarioActual();',
    'usuarioActual = obtenerUsuarioActual();'
  );
}
vm.runInContext(codigo, contexto);
(async () => {
  await alCargarDOM();
  const celdas = elementos.tablaUsuarios.children[0].children;
  assert.strictEqual(celdas[6].children[0].children.length, 3);
  console.log('ok');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    resultado = subprocess.run(
        [NODE, "-e", guion, ruta], capture_output=True, text=True, timeout=30
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "ok"
    mutacion = subprocess.run(
        [NODE, "-e", guion, ruta, "sin-await"], capture_output=True, text=True, timeout=30
    )
    assert mutacion.returncode != 0


@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
def test_confirmacion_devuelve_el_foco_a_una_accion_vigente_si_se_elimina_el_origen():
    ruta = os.path.join(RAIZ, "frontend", "assets", "js", "confirmar.js")
    guion = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
function fijarConexion(elemento, conectada) {
  elemento.isConnected = conectada;
  elemento.children.forEach(hijo => fijarConexion(hijo, conectada));
}
class Element {
  constructor(tag, doc, focusable = false) {
    this.tagName = tag;
    this.doc = doc;
    this.focusable = focusable;
    this.children = [];
    this.attributes = {};
    this.handlers = {};
    this.isConnected = false;
    this.disabled = false;
  }
  appendChild(child) {
    child.parentElement = this;
    fijarConexion(child, this.isConnected);
    this.children.push(child);
    return child;
  }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  addEventListener(name, callback) { this.handlers[name] = callback; }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name] || null; }
  hasAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attributes, name); }
  querySelector() {
    for (const child of this.children) {
      if (child.focusable && !child.disabled && child.isConnected) return child;
      const nested = child.querySelector();
      if (nested) return nested;
    }
    return null;
  }
  focus(options) {
    if (!this.isConnected || this.disabled) return;
    this.doc.activeElement = this;
    this.lastFocus = options;
  }
  remove() {
    if (this.parentElement) {
      this.parentElement.children = this.parentElement.children.filter(child => child !== this);
    }
    this.parentElement = null;
    fijarConexion(this, false);
  }
  click() { this.handlers.click(); }
}
const document = {
  activeElement: null,
  listeners: {},
  createElement: tag => new Element(tag, document),
  addEventListener: (name, callback) => { document.listeners[name] = callback; },
  removeEventListener: name => { delete document.listeners[name]; },
  querySelector: () => heading
};
document.body = new Element('body', document);
document.body.isConnected = true;
const main = new Element('main', document);
const heading = new Element('h1', document);
const row = new Element('tr', document);
const opener = new Element('button', document, true);
const sibling = new Element('button', document, true);
row.append(opener, sibling);
main.append(heading, row);
document.body.appendChild(main);
document.activeElement = opener;
const contexto = { document, window: {}, console };
vm.createContext(contexto);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), contexto);
(async () => {
  const pendiente = contexto.window.confirmarAccion('Confirmar', 'normal');
  opener.remove();
  const fondo = document.body.children.find(elemento => elemento.className === 'confirmacion-fondo');
  const aceptar = fondo.children[0].children[2].children[1];
  aceptar.click();
  await pendiente;
  assert.strictEqual(document.activeElement, sibling);
  assert.strictEqual(sibling.lastFocus.preventScroll, true);
  console.log('ok');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    resultado = subprocess.run(
        [NODE, "-e", guion, ruta], capture_output=True, text=True, timeout=30
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "ok"


def test_datos_de_usuario_permiten_dividir_correos_largos_en_movil():
    for pantalla in ("asignar_rol", "desactivar_usuario"):
        css = leer("frontend", "usuarios", f"{pantalla}.css")
        regla = re.search(r"\.datos p\s*\{([^}]*)\}", css, re.S)
        assert regla and re.search(r"overflow-wrap:\s*anywhere\s*;", regla.group(1)), pantalla


@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
def test_filas_de_usuario_conservan_etiquetas_y_fecha_para_vista_responsiva():
    ruta = os.path.join(RAIZ, "frontend", "usuarios", "usuarios.js")
    guion = r"""
const fs = require('fs'), vm = require('vm');
class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.classList = { add: value => { this.className = value; } };
    this.options = [];
    this.value = '';
  }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) {
    this.children = children;
    if (this.tagName === 'select') this.options = children;
  }
  addEventListener(evento, callback) {
    if (evento === 'DOMContentLoaded') this.domContentLoaded = callback;
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name] || null; }
  querySelector() { return elementos.botonRegistrar; }
}
const ids = ['formUsuario','mensaje','id_rol','id_area','tablaUsuarios',
  'mensajeListadoUsuarios','filtroRol','filtroArea','filtroEstado','ordenUsuarios',
  'btnNuevoUsuario','panelNuevoUsuario','nombres','btnCerrarNuevoUsuario','email','password'];
const elementos = Object.fromEntries(ids.map(id => [id, new Element(id.startsWith('filtro') || id === 'ordenUsuarios' || id.startsWith('id_') ? 'select' : 'div')]));
elementos.botonRegistrar = new Element('button');
let configuracionPanel;
let alCargarDOM;
const contexto = {
  window: { API_CONFIG: { API_URL: 'http://local', credentials: 'include' } },
  document: {
    getElementById: id => elementos[id] || null,
    createElement: tag => new Element(tag),
    addEventListener: (evento, callback) => { if (evento === 'DOMContentLoaded') alCargarDOM = callback; }
  },
  configurarPanelAlta: configuracion => { configuracionPanel = configuracion; },
  obtenerUsuarioActual: async () => ({ nombre_rol: process.argv[2] }),
  nombreRolNatural: value => value,
  fetch: async () => ({ ok: true, json: async () => [] }),
  URLSearchParams,
  Option: function(text, value) { this.text = text; this.value = value; }
};
vm.createContext(contexto);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), contexto);
(async () => {
  await alCargarDOM();
  elementos.mensaje.textContent = 'Usuario registrado correctamente';
  elementos.mensaje.className = 'mensaje success';
  configuracionPanel.alAbrir();
  contexto.mostrarUsuarios([{
    id_usuario: 14, nombres: 'Prueba Móvil', email: 'persona@nahan.local',
    nombre_rol: 'USUARIO_AREA_JURIDICA', nombre_area: 'Jurídica',
    estado: 'ACTIVO', fecha_creacion: '2026-11-05 10:30:00'
  }]);
  const celdas = elementos.tablaUsuarios.children[0].children;
  console.log(JSON.stringify(celdas.map(celda => ({
    label: celda.dataset.label, text: celda.textContent, children: celda.children.length,
    links: celda.children[0] ? celda.children[0].children.length : 0
  })).concat([{
    label: 'mensaje',
    text: elementos.mensaje.textContent,
    className: elementos.mensaje.className
  }])));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    for rol in ("ADMINISTRADOR", "USUARIO_AREA_JURIDICA", "USUARIO_AREA_CONTABLE"):
        resultado = subprocess.run(
            [NODE, "-e", guion, ruta, rol], capture_output=True, text=True, timeout=30
        )
        assert resultado.returncode == 0, resultado.stderr
        celdas = json.loads(resultado.stdout)
        assert [celda["label"] for celda in celdas[:7]] == [
            "Nombre", "Correo electrónico", "Rol", "Área", "Estado", "Fecha de registro", "Acciones"
        ]
        assert celdas[5]["text"] == "05-11-2026 10:30"
        if rol == "ADMINISTRADOR":
            assert celdas[6]["children"] == 1 and celdas[6]["links"] == 3
        else:
            assert celdas[6]["children"] == 0 and celdas[6]["links"] == 0
        assert celdas[7] == {"label": "mensaje", "text": "", "className": "mensaje"}


def test_usuarios_adapta_tabla_a_columnas_y_tarjetas_por_ancho():
    css = leer("frontend", "usuarios", "usuarios.css")
    rango_intermedio = re.search(
        r"@media\s*\(min-width:\s*769px\)\s*and\s*\(max-width:\s*1100px\)\s*\{(.*?)\n\}",
        css, re.S
    )
    movil = re.search(r"@media\s*\(max-width:\s*768px\)\s*\{(.*)", css, re.S)
    assert rango_intermedio and movil
    assert "table-layout: fixed" in rango_intermedio.group(1)
    assert ".usuarios-tabla th:nth-child(6)" in rango_intermedio.group(1)
    assert ".usuarios-tabla td:nth-child(6)" in rango_intermedio.group(1)
    assert "display: none" in rango_intermedio.group(1)
    assert ".usuarios-tabla tbody tr" in movil.group(1)
    assert "display: block" in movil.group(1)
    assert "content: attr(data-label)" in movil.group(1)
    assert "min-width: 0" in movil.group(1)


@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
def test_acciones_por_fila_generan_destino_etiqueta_clase_y_id_codificado():
    ruta = os.path.join(RAIZ, "frontend", "usuarios", "usuarios.js")
    guion = r"""
const fs = require('fs'), vm = require('vm');
class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.options = [];
    this.value = '';
    this.classList = { add() {} };
  }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this.options = children; }
  addEventListener() {}
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name] || null; }
  querySelector() { return new Element('button'); }
}
const ids = ['formUsuario','mensaje','id_rol','id_area','tablaUsuarios',
  'mensajeListadoUsuarios','filtroRol','filtroArea','filtroEstado','ordenUsuarios'];
const elementos = Object.fromEntries(ids.map(id => [id, new Element('select')]));
elementos.formUsuario = new Element('form');
const contexto = {
  window: { API_CONFIG: { API_URL: 'http://local', credentials: 'include' } },
  document: {
    getElementById: id => elementos[id] || null,
    createElement: tag => new Element(tag),
    addEventListener() {}
  },
  configurarPanelAlta() {},
  nombreRolNatural: value => value,
  fetch: async () => ({ ok: true, json: async () => [] }),
  URLSearchParams,
  Option: function(text, value) { this.text = text; this.value = value; }
};
vm.createContext(contexto);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), contexto);
function enlaces(usuario) {
  return contexto.crearCeldaAcciones(usuario).children[0].children.map(enlace => ({
    text: enlace.textContent,
    href: enlace.href,
    className: enlace.className,
    ariaLabel: enlace.getAttribute('aria-label')
  }));
}
console.log(JSON.stringify({
  activo: enlaces({ id_usuario: '9&2', nombres: 'Alicia Ejemplo', estado: 'ACTIVO' }),
  inactivo: enlaces({ id_usuario: 7, nombres: 'Bruno Ejemplo', estado: 'INACTIVO' })
}));
"""
    resultado = subprocess.run(
        [NODE, "-e", guion, ruta], capture_output=True, text=True, timeout=30
    )
    assert resultado.returncode == 0, resultado.stderr
    datos = json.loads(resultado.stdout)
    assert datos["activo"] == [
        {
            "text": "Editar",
            "href": "modificar_usuario.html?id=9%262",
            "className": "btn btn-primary btn-small",
            "ariaLabel": "Editar a Alicia Ejemplo"
        },
        {
            "text": "Asignar rol",
            "href": "asignar_rol.html?id=9%262",
            "className": "btn btn-secondary btn-small",
            "ariaLabel": "Asignar rol a Alicia Ejemplo"
        },
        {
            "text": "Deshabilitar",
            "href": "desactivar_usuario.html?id=9%262",
            "className": "btn btn-warning btn-small",
            "ariaLabel": "Deshabilitar a Alicia Ejemplo"
        }
    ]
    assert [enlace["text"] for enlace in datos["inactivo"]] == ["Editar", "Asignar rol"]


@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
def test_ids_de_url_solo_consultan_ids_validos_y_cargan_el_usuario_solicitado():
    rutas = [
        os.path.join(RAIZ, "frontend", "usuarios", "asignar_rol.js"),
        os.path.join(RAIZ, "frontend", "usuarios", "desactivar_usuario.js")
    ]
    guion = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const rutas = process.argv.slice(1);
function crearEscenario(ruta, id) {
  const elementos = {};
  class Element {
    constructor() {
      this.value = '';
      this.textContent = '';
      this.className = '';
      this.classes = new Set(['hidden']);
      this.classList = {
        add: nombre => this.classes.add(nombre),
        remove: nombre => this.classes.delete(nombre)
      };
    }
  }
  const obtener = nombre => elementos[nombre] || (elementos[nombre] = new Element());
  const llamadas = [];
  let listo;
  const usuario = {
    id_usuario: 9, nombres: 'Usuario Nueve', email: 'nueve@nahan.local',
    id_rol: 2, nombre_rol: 'USUARIO_AREA_JURIDICA',
    nombre_area: 'JURIDICA', estado: 'ACTIVO'
  };
  const contexto = {
    window: {
      location: { search: id === null ? '' : `?id=${encodeURIComponent(id)}` },
      API_CONFIG: { API_URL: '/api', credentials: 'include' }
    },
    URLSearchParams,
    document: {
      getElementById: obtener,
      addEventListener: (evento, callback) => { if (evento === 'DOMContentLoaded') listo = callback; }
    },
    UsuariosAutocomplete: {
      configurarSelectorUsuario() {},
      mostrarUsuarioEnInput(inputId, hiddenId, data) {
        obtener(inputId).value = data.nombres;
        obtener(hiddenId).value = String(data.id_usuario);
      }
    },
    nombreRolNatural: value => value,
    fetch: async url => {
      llamadas.push(url);
      return { ok: true, json: async () => usuario };
    },
    console
  };
  vm.createContext(contexto);
  vm.runInContext(fs.readFileSync(ruta, 'utf8'), contexto);
  return Promise.resolve(listo()).then(() => new Promise(resolve => setImmediate(() => resolve({
    llamadas,
    nombre: obtener('nombres').textContent,
    correo: obtener('email').textContent,
    idSeleccionado: obtener('id_usuario').value,
    visible: !obtener('datosUsuario').classes.has('hidden'),
    rol: obtener('rol_actual').textContent,
    estado: obtener('estado').textContent
  }))));
}
(async () => {
  for (const ruta of rutas) {
    for (const invalido of ['abc', '0', '-5']) {
      const resultado = await crearEscenario(ruta, invalido);
      assert.deepStrictEqual(resultado.llamadas, [], `${ruta}: ${invalido} no debe consultar`);
      assert.strictEqual(resultado.visible, false);
    }
    const resultado = await crearEscenario(ruta, '9');
    assert.deepStrictEqual(resultado.llamadas, ['/api/usuarios/9']);
    assert.strictEqual(resultado.nombre, 'Usuario Nueve');
    assert.strictEqual(resultado.correo, 'nueve@nahan.local');
    assert.strictEqual(resultado.idSeleccionado, '9');
    assert.strictEqual(resultado.visible, true);
    if (ruta.includes('asignar_rol')) assert.strictEqual(resultado.rol, 'USUARIO_AREA_JURIDICA');
    else assert.strictEqual(resultado.estado, 'ACTIVO');
  }
  console.log('ok');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    resultado = subprocess.run(
        [NODE, "-e", guion, *rutas], capture_output=True, text=True, timeout=30
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "ok"


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
    # El contenedor se muestra para todos los roles: además de los enlaces de administración
    # aloja el botón de registro manual, que pueden usar los tres roles.
    assert "accionesControlHoras.hidden = false" not in bloque
    assert "accionesControlHoras.hidden = false" in js
    assert js.index('botonRegistroManual.id = "btnRegistroManual"') < js.index(
        'if (usuarioActual.nombre_rol === "ADMINISTRADOR") {'
    )


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
