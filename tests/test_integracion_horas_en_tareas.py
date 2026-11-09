"""Integración de las horas con el detalle de la tarea y con Control de horas.

Cubre los requisitos que piden el registro de tiempo desde la tarea: RF71 («iniciar el temporizador desde
la vista detalle de la tarea»), RF72/RF73 (historial y total por tarea; desglose por usuario para el
administrador) y los casos de uso CU-14 y CU-29 («abre el detalle de la tarea y habilita el botón para
ingresar tiempo»). Parte estática, y parte de comportamiento: se ejecutan detalle_tarea.js y
control_horas.js con Node y un DOM simulado. El servidor sigue siendo quien decide permisos y reglas;
aquí se comprueba que la pantalla muestre y envíe lo correcto.
"""
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


HTML = leer("frontend", "tareas", "detalle_tarea.html")
JS = leer("frontend", "tareas", "detalle_tarea.js")
CSS = leer("frontend", "tareas", "tareas.css")
JS_HORAS = leer("frontend", "control_horas", "control_horas.js")


# ---------------------------------------------------------------------------
# Estructura
# ---------------------------------------------------------------------------
def test_el_detalle_de_la_tarea_tiene_la_seccion_de_horas_entre_los_antecedentes_y_el_historial():
    assert HTML.index('id="detalleContenido"') < HTML.index('id="seccionHoras"') < HTML.index('id="seccionHistorial"')
    seccion = re.search(r'<section[^>]*id="seccionHoras"[^>]*>(.*?)</section>', HTML, re.S).group(1)

    assert 'id="seccionHoras" hidden' in HTML and 'aria-labelledby="tituloHoras"' in HTML
    assert 'id="tituloHoras"' in seccion
    for identificador in (
        "btnIniciarTemporizadorTarea", "enlaceRegistroManualTarea", "enlaceControlHorasTarea",
        "horasEstadoTemporizador", "horasMensaje", "horasTotalTarea", "horasMontoTarea",
        "horasRegistrosTarea", "tablaHorasTarea", "thUsuarioHoras", "horasNota", "horasAlcance",
    ):
        assert f'id="{identificador}"' in seccion, identificador
    assert 'id="btnIniciarTemporizadorTarea" class="btn btn-primary" hidden' in seccion
    assert 'id="enlaceRegistroManualTarea" class="btn btn-secondary" href="#" hidden' in seccion
    assert 'id="thUsuarioHoras" hidden' in seccion, "la columna de usuario solo la ve el administrador"
    assert 'id="horasEstadoTemporizador" class="form-help" aria-live="polite"' in seccion
    assert 'id="horasMensaje" class="mensaje" aria-live="polite"' in seccion


def test_la_logica_de_horas_solo_usa_los_endpoints_de_control_de_horas_y_texto_plano():
    bloque = JS[JS.index("// Horas trabajadas en la tarea"):]

    assert "`${API_URL}/control-horas/registros?id_tarea=${idTarea}`" in bloque
    assert "`${API_URL}/control-horas/contexto`" in bloque
    assert "`${API_URL}/control-horas/iniciar`" in bloque
    assert 'method: "POST"' in bloque and '"Content-Type": "application/json"' in bloque
    assert "body: JSON.stringify({ id_tarea: idTarea })" in bloque, "el POST declara JSON y trae cuerpo"
    assert "innerHTML" not in JS, "los datos de usuario (la observación) se muestran como texto"
    assert JS.index("await cargarAdjuntos(idTarea);") < JS.index("await cargarHoras(tarea);")
    assert "if (!seccion) return;" in bloque, "con un HTML anterior en caché la sección no existe y no debe fallar"


def test_los_estilos_de_horas_son_responsivos():
    assert ".horas-resumen" in CSS
    assert re.search(r"@media \(max-width: 640px\)\s*\{\s*\.horas-resumen\s*\{\s*grid-template-columns: minmax\(0, 1fr\)", CSS)
    assert "overflow-wrap: anywhere" in CSS[CSS.index(".horas-origen-observacion"):][:200]


def test_control_de_horas_acepta_la_tarea_solicitada_y_avisa_de_una_pagina_anterior():
    assert "const ELEMENTOS_REQUERIDOS = [" in JS_HORAS
    for identificador in ("accionesControlHoras", "formFiltrosHoras", "panelRegistroManual", "formRegistroManual"):
        assert f'"{identificador}"' in JS_HORAS[JS_HORAS.index("const ELEMENTOS_REQUERIDOS"):][:260]
    comprobacion = JS_HORAS.index("ELEMENTOS_REQUERIDOS.some(")
    assert comprobacion < JS_HORAS.index('const accionesControlHoras = document.getElementById("accionesControlHoras");')
    assert "/^[1-9][0-9]{0,9}$/.test(id)" in JS_HORAS, "solo se acepta un identificador numérico"
    assert 'parametros.get("registrar") === "manual"' in JS_HORAS


# ---------------------------------------------------------------------------
# Comportamiento (Node)
# ---------------------------------------------------------------------------
PRELUDIO = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
process.on('unhandledRejection', error => { console.error('RECHAZO SIN ATENDER', error); process.exit(3); });

const elementos = {};
const ausentes = new Set();
function crear(id) {
  let texto = '';
  const e = {
    id, value: '', className: '', hidden: false, disabled: false, href: '', type: '', max: '', min: '', colSpan: 1,
    focusCount: 0, children: [], selectedOptions: [{ textContent: '' }], atributos: {}, onclick: null,
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    addEventListener(nombre, fn) { (this.eventos = this.eventos || {})[nombre] = fn; },
    setAttribute(n, v) { this.atributos[n] = v; }, getAttribute(n) { return this.atributos[n] ?? null; }, reset() {},
    appendChild(h) { this.children.push(h); return h; },
    insertBefore(h, ref) { this.children.unshift(h); return h; },
    focus() { this.focusCount += 1; }
  };
  Object.defineProperty(e, 'textContent', { get: () => texto, set: v => { texto = v; e.children.length = 0; } });
  return e;
}
const obtener = id => ausentes.has(id) ? null : (elementos[id] = elementos[id] || crear(id));
const manejadores = {};
const llamadas = [];
const respuestas = { };
const ubicacion = { href: '', search: '' };
const cuerpo = (estado, datos) => ({ ok: estado < 400, status: estado, json: async () => datos, text: async () => JSON.stringify(datos) });

const ctx = vm.createContext({
  document: {
    getElementById: obtener, createElement: tag => crear(tag), querySelector: () => crear('qs'),
    addEventListener(nombre, fn) { manejadores[nombre] = fn; }, body: crear('body'), currentScript: null
  },
  window: { API_CONFIG: { API_URL: '/api', credentials: 'include' }, location: ubicacion, history: {} },
  console, Intl, Date, Math, Number, String, JSON, Map, Array, Promise, URLSearchParams, setTimeout,
  setInterval: () => 0, clearInterval() {},
  fetch: async (url, opciones) => {
    llamadas.push({ url, opciones });
    for (const [prefijo, resp] of Object.entries(respuestas)) if (url.includes(prefijo)) return typeof resp === 'function' ? resp(url, opciones) : resp;
    return cuerpo(200, {});
  },
  // Marca las conversiones a UTC: el inicio del temporizador llega como hora local y no debe convertirse.
  formatearFechaHora24: (v, o) => (o && o.utc ? 'UTC ' : '') + String(v).replace('T', ' ').slice(0, 16),
  obtenerUsuarioActual: async () => ctx.__usuario,
  confirmarAccion: async () => true, avisarAccion: async () => {},
  configurarPanelAlta: () => ({ abrir() { ctx.__panelAbierto = (ctx.__panelAbierto || 0) + 1; }, cerrar() {}, estaAbierto: () => true })
});
const fetchOriginal = ctx.fetch;
window = ctx.window;
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const ejecutar = codigo => vm.runInContext(codigo, ctx);
const dormir = ms => new Promise(r => setTimeout(r, ms));
function reiniciar() {
  // Los scripts guardan los elementos al cargarse: se reinicia su estado sin cambiar su identidad.
  for (const e of Object.values(elementos)) {
    e.value = ''; e.className = ''; e.hidden = false; e.disabled = false; e.href = ''; e.colSpan = 1;
    e.textContent = ''; e.onclick = null; e.atributos = {}; e.focusCount = 0;
  }
  ausentes.clear(); llamadas.length = 0; ubicacion.href = ''; ubicacion.search = ''; ctx.fetch = fetchOriginal;
  for (const k of Object.keys(respuestas)) delete respuestas[k];
}
"""


def ejecutar_node(archivo_js, guion):
    ruta = os.path.join(RAIZ, *archivo_js)
    resultado = subprocess.run(
        [NODE, "-e", PRELUDIO + guion, ruta], capture_output=True, text=True, timeout=60, cwd=RAIZ
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert resultado.stdout.strip().endswith("OK")


GUION_DETALLE = r"""
const TAREA = { id_tarea: 1, id_cliente: 7, titulo: 'Contrato', estado: 'EN_PROCESO' };
const registro = (n, extra = {}) => ({ id_registro: n, fecha: '07-11-2026', inicio_hora: '09:00:00', fin: '10:00:00',
  duracion_minutos: 60, monto: 45000, origen: 'TEMPORIZADOR', observacion: null, usuario_responsable: 'Ana', ...extra });
const contexto = (tareas, activo = null) => cuerpo(200, { tareas, temporizador_activo: activo });
const t = id => obtener(id).textContent;

(async () => {
  // 1) Usuario de área con la tarea habilitada y sin horas.
  reiniciar(); ctx.__usuario = { id_usuario: 4, nombre_rol: 'USUARIO_AREA_JURIDICA' };
  respuestas['/registros?id_tarea=1'] = cuerpo(200, { registros: [], resumen: { minutos_acumulados: 0, monto_acumulado: 0, total_registros: 0 } });
  respuestas['/control-horas/contexto'] = contexto([{ id_tarea: 1 }]);
  await ejecutar('cargarHoras(' + JSON.stringify(TAREA) + ')');
  assert.strictEqual(elementos.seccionHoras.hidden, false);
  assert.strictEqual(t('horasAlcance'), 'Sus horas registradas en esta tarea.');
  assert.strictEqual(elementos.thUsuarioHoras.hidden, true, 'sin columna de usuario');
  assert.strictEqual(elementos.btnIniciarTemporizadorTarea.hidden, false);
  assert.strictEqual(elementos.btnIniciarTemporizadorTarea.disabled, false);
  assert.strictEqual(elementos.enlaceRegistroManualTarea.hidden, false);
  assert.strictEqual(elementos.enlaceRegistroManualTarea.href, '../control_horas/control_horas.html?id_tarea=1&registrar=manual');
  assert.strictEqual(elementos.enlaceControlHorasTarea.href, '../control_horas/control_horas.html?id_tarea=1');
  assert.ok(t('tablaHorasTarea') === '' && elementos.tablaHorasTarea.children[0].children[0].textContent.includes('Todavía no hay horas'));
  assert.strictEqual(elementos.tablaHorasTarea.children[0].children[0].colSpan, 6);
  assert.deepStrictEqual([t('horasTotalTarea'), t('horasRegistrosTarea')], ['00h 00m', '0']);
  assert.ok(llamadas.every(l => !l.opciones || l.opciones.method === undefined), 'cargar la sección solo lee');

  // 2) Administrador: todas las horas, columna de usuario, 10 filas como máximo y la observación como texto.
  reiniciar(); ctx.__usuario = { id_usuario: 1, nombre_rol: 'ADMINISTRADOR' };
  const muchos = Array.from({ length: 12 }, (_, i) => registro(i + 1, i === 0 ? { origen: 'MANUAL', observacion: '<img src=x onerror=alert(1)>' } : {}));
  respuestas['/registros?id_tarea=1'] = cuerpo(200, { registros: muchos, resumen: { minutos_acumulados: 750, monto_acumulado: 562500, total_registros: 12 } });
  respuestas['/control-horas/contexto'] = contexto([{ id_tarea: 1 }]);
  await ejecutar('cargarHoras(' + JSON.stringify(TAREA) + ')');
  assert.strictEqual(t('horasAlcance'), 'Horas registradas por todos los usuarios en esta tarea.');
  assert.strictEqual(elementos.thUsuarioHoras.hidden, false);
  assert.strictEqual(elementos.tablaHorasTarea.children.length, 10, 'solo los 10 más recientes');
  assert.ok(t('horasNota').includes('10 registros más recientes de 12'));
  assert.deepStrictEqual([t('horasTotalTarea'), t('horasRegistrosTarea')], ['12h 30m', '12'], 'el total incluye todos');
  assert.ok(t('horasMontoTarea').includes('562.500'));
  const primera = elementos.tablaHorasTarea.children[0].children;
  assert.strictEqual(primera.length, 7, 'con la columna de usuario');
  assert.strictEqual(primera[1].textContent, 'Ana');
  assert.strictEqual(primera[6].children[0].textContent, 'Manual');
  assert.strictEqual(primera[6].children[1].textContent, '<img src=x onerror=alert(1)>', 'se muestra como texto');

  // 3) Temporizador en curso en esta misma tarea.
  reiniciar(); ctx.__usuario = { id_usuario: 4, nombre_rol: 'USUARIO_AREA_JURIDICA' };
  respuestas['/registros?id_tarea=1'] = cuerpo(200, { registros: [], resumen: {} });
  respuestas['/control-horas/contexto'] = contexto([{ id_tarea: 1 }], { id_tarea: 1, tarea: 'Contrato', inicio: '2026-11-08T22:53:10' });
  await ejecutar('cargarHoras(' + JSON.stringify(TAREA) + ')');
  assert.strictEqual(elementos.btnIniciarTemporizadorTarea.hidden, true);
  assert.ok(t('horasEstadoTemporizador').includes('en curso en esta tarea desde 2026-11-08 22:53'), t('horasEstadoTemporizador'));
  assert.strictEqual(elementos.enlaceRegistroManualTarea.hidden, false, 'se puede registrar el pasado con el temporizador en curso');

  // 4) Temporizador en curso en OTRA tarea: no se puede iniciar otro.
  reiniciar();
  respuestas['/registros?id_tarea=1'] = cuerpo(200, { registros: [], resumen: {} });
  respuestas['/control-horas/contexto'] = contexto([{ id_tarea: 1 }, { id_tarea: 2 }], { id_tarea: 2, tarea: 'Otra tarea', inicio: '2026-11-08T22:53:10' });
  await ejecutar('cargarHoras(' + JSON.stringify(TAREA) + ')');
  assert.strictEqual(elementos.btnIniciarTemporizadorTarea.hidden, false);
  assert.strictEqual(elementos.btnIniciarTemporizadorTarea.disabled, true);
  assert.ok(t('horasEstadoTemporizador').includes('«Otra tarea»'));

  // 5) La tarea no está habilitada (finalizada, cliente inactivo o ajena): sin acciones y con el motivo.
  reiniciar();
  respuestas['/registros?id_tarea=1'] = cuerpo(200, { registros: [], resumen: {} });
  respuestas['/control-horas/contexto'] = contexto([{ id_tarea: 2 }]);
  await ejecutar('cargarHoras(' + JSON.stringify({ ...TAREA, estado: 'COMPLETADA' }) + ')');
  assert.strictEqual(elementos.seccionHoras.hidden, false, 'el historial se sigue viendo');
  assert.strictEqual(elementos.btnIniciarTemporizadorTarea.hidden, true);
  assert.strictEqual(elementos.enlaceRegistroManualTarea.hidden, true);
  assert.ok(t('horasEstadoTemporizador').includes('No se pueden registrar horas en esta tarea'));

  // 6) Falla Control de horas: no se ofrecen acciones que el servidor podría rechazar.
  reiniciar();
  respuestas['/registros?id_tarea=1'] = cuerpo(500, { error: 'Error interno al listar registros de horas.' });
  respuestas['/control-horas/contexto'] = cuerpo(500, { error: 'x' });
  await ejecutar('cargarHoras(' + JSON.stringify(TAREA) + ')');
  assert.strictEqual(elementos.seccionHoras.hidden, false);
  assert.strictEqual(t('horasMensaje'), 'Error interno al listar registros de horas.');
  assert.strictEqual(elementos.horasMensaje.className, 'mensaje error');
  assert.strictEqual(elementos.btnIniciarTemporizadorTarea.hidden, true);
  assert.strictEqual(elementos.enlaceRegistroManualTarea.hidden, true);
  assert.ok(t('horasEstadoTemporizador').includes('No se pudo comprobar'));

  // 7) Sin red: mensaje, sin excepciones.
  reiniciar();
  ctx.fetch = async () => { throw new Error('sin red'); };
  const consola = console.error; console.error = () => {};
  await ejecutar('cargarHoras(' + JSON.stringify(TAREA) + ')');
  console.error = consola;
  assert.strictEqual(t('horasMensaje'), 'No se pudieron cargar las horas de la tarea.');

  // 8) HTML anterior en caché (sin la sección) o sin sesión: no hace nada ni falla.
  reiniciar(); ctx.fetch = async (url, o) => { llamadas.push({ url, o }); return cuerpo(200, {}); };
  ausentes.add('seccionHoras');
  await ejecutar('cargarHoras(' + JSON.stringify(TAREA) + ')');
  assert.strictEqual(llamadas.length, 0, 'sin la sección no consulta nada');
  reiniciar(); ctx.__usuario = null;
  await ejecutar('cargarHoras(' + JSON.stringify(TAREA) + ')');
  assert.strictEqual(llamadas.length, 0, 'sin sesión no consulta nada');

  // 9) Iniciar el temporizador desde el detalle: POST con cuerpo JSON y luego Control de horas.
  reiniciar(); ctx.__usuario = { id_usuario: 4, nombre_rol: 'USUARIO_AREA_JURIDICA' };
  respuestas['/registros?id_tarea=1'] = cuerpo(200, { registros: [], resumen: {} });
  respuestas['/control-horas/contexto'] = contexto([{ id_tarea: 1 }]);
  respuestas['/control-horas/iniciar'] = cuerpo(201, { message: 'Temporizador iniciado correctamente.' });
  await ejecutar('cargarHoras(' + JSON.stringify(TAREA) + ')');
  await elementos.btnIniciarTemporizadorTarea.onclick();
  const envio = llamadas.find(l => l.url.endsWith('/control-horas/iniciar'));
  assert.strictEqual(envio.opciones.method, 'POST');
  assert.strictEqual(envio.opciones.headers['Content-Type'], 'application/json');
  assert.deepStrictEqual(JSON.parse(envio.opciones.body), { id_tarea: 1 });
  assert.strictEqual(ubicacion.href, '../control_horas/control_horas.html');

  // 10) El servidor lo rechaza (409): se muestra el motivo, no se navega y se puede reintentar.
  ubicacion.href = '';
  respuestas['/control-horas/iniciar'] = cuerpo(409, { error: 'Ya existe un temporizador activo para este usuario.' });
  await elementos.btnIniciarTemporizadorTarea.onclick();
  assert.strictEqual(t('horasMensaje'), 'Ya existe un temporizador activo para este usuario.');
  assert.strictEqual(ubicacion.href, '');
  assert.strictEqual(elementos.btnIniciarTemporizadorTarea.disabled, false);
  assert.strictEqual(t('btnIniciarTemporizadorTarea'), 'Iniciar temporizador');
  console.log('OK');
})().catch(error => { console.error(error); process.exit(1); });
"""


@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
def test_el_detalle_de_la_tarea_muestra_las_horas_y_permite_registrar_segun_el_servidor():
    ejecutar_node(("frontend", "tareas", "detalle_tarea.js"), GUION_DETALLE)


GUION_CONTROL = r"""
const usuario = { id_usuario: 4, nombre_rol: 'USUARIO_AREA_JURIDICA' };
const tareas = [
  { id_tarea: 11, id_cliente: 7, titulo: 'Declaración mensual', descripcion: '', cliente: 'Cliente Uno', cliente_rut: '11.111.111-1' },
  { id_tarea: 12, id_cliente: 7, titulo: 'Balance', descripcion: '', cliente: 'Cliente Uno', cliente_rut: '11.111.111-1' }
];
const t = id => obtener(id).textContent;
async function cargarPagina(busqueda, { activo = null, enHistorial = [] } = {}) {
  reiniciar(); ctx.__usuario = usuario; ubicacion.search = busqueda; ctx.__panelAbierto = 0;
  respuestas['/control-horas/contexto'] = cuerpo(200, { tareas, temporizador_activo: activo });
  respuestas['/control-horas/filtros'] = cuerpo(200, { clientes: [], tareas: enHistorial, usuarios: [] });
  respuestas['/control-horas/registros'] = cuerpo(200, { registros: [], resumen: {} });
  await manejadores.DOMContentLoaded();
  await dormir(20);
}

(async () => {
  // Solicitud: solo se aceptan identificadores numéricos positivos.
  const lee = b => { ubicacion.search = b; return JSON.parse(JSON.stringify(ejecutar('leerSolicitudDeTarea()'))); };
  assert.deepStrictEqual(lee('?id_tarea=11'), { idTarea: 11, registrarManual: false });
  assert.deepStrictEqual(lee('?id_tarea=11&registrar=manual'), { idTarea: 11, registrarManual: true });
  assert.deepStrictEqual(lee('?id_tarea=11&registrar=otra'), { idTarea: 11, registrarManual: false });
  for (const malo of ['', '?id_tarea=', '?id_tarea=0', '?id_tarea=-1', '?id_tarea=abc', '?id_tarea=1%20OR%201=1', '?id_tarea=12345678901', '?id_tarea=1.5']) {
    assert.strictEqual(lee(malo), null, malo);
  }

  // Página normal (sin solicitud): se carga todo y nada cambia.
  await cargarPagina('');
  assert.ok(llamadas.some(l => l.url.includes('/control-horas/contexto')) && llamadas.some(l => l.url.includes('/control-horas/registros')));
  assert.strictEqual(obtener('idTareaSeleccionada').value, '');
  assert.strictEqual(ctx.__panelAbierto, 0);
  assert.strictEqual(t('mensajeControl'), '');

  // Desde el detalle de la tarea: se preselecciona para iniciar el temporizador.
  await cargarPagina('?id_tarea=12');
  assert.strictEqual(obtener('idTareaSeleccionada').value, 12);
  assert.strictEqual(obtener('idClienteSeleccionado').value, 7);
  assert.ok(obtener('tareaBusqueda').value.includes('Balance') && obtener('clienteBusqueda').value.includes('Cliente Uno'));
  assert.strictEqual(elementos.btnIniciar.disabled, false, 'se puede iniciar con un clic');
  assert.strictEqual(ctx.__panelAbierto, 0, 'sin ?registrar=manual el panel sigue cerrado');

  // Con registros de esa tarea, el historial queda filtrado por ella.
  await cargarPagina('?id_tarea=12', { enHistorial: [{ id_tarea: 12, id_cliente: 7, titulo: 'Balance', cliente: 'Cliente Uno' }] });
  assert.strictEqual(elementos.filtroTarea.value, '12');
  assert.strictEqual(elementos.filtroCliente.value, '7');
  const registros = llamadas.filter(l => l.url.includes('/control-horas/registros')).pop();
  assert.ok(registros.url.includes('id_tarea=12') && registros.url.includes('id_cliente=7'), registros.url);

  // Registro manual desde el detalle: abre el panel con cliente y tarea ya elegidos y el foco en la hora.
  await cargarPagina('?id_tarea=12&registrar=manual');
  assert.strictEqual(ctx.__panelAbierto, 1);
  assert.strictEqual(elementos.rmCliente.value, '7');
  assert.strictEqual(elementos.rmTarea.value, '12');
  assert.ok(elementos.rmHoraInicio.focusCount >= 1);

  // Tarea no disponible: mensaje claro y sin preseleccionar ni abrir nada.
  await cargarPagina('?id_tarea=99&registrar=manual');
  assert.ok(t('mensajeControl').includes('no está disponible para registrar horas'), t('mensajeControl'));
  assert.strictEqual(elementos.mensajeControl.className, 'mensaje info');
  assert.strictEqual(obtener('idTareaSeleccionada').value, '');
  assert.strictEqual(ctx.__panelAbierto, 0);

  // Con un temporizador en curso no se pisa la tarea activa.
  const activo = { id_tarea: 11, id_cliente: 7, tarea: 'Declaración mensual', cliente: 'Cliente Uno', cliente_rut: '11.111.111-1', descripcion: '', inicio: '2026-11-08T22:00:00', activo: true };
  await cargarPagina('?id_tarea=12', { activo });
  assert.strictEqual(obtener('idTareaSeleccionada').value, 11, 'sigue la tarea del temporizador activo');

  // HTML anterior en caché: avisa y no consulta nada (antes quedaba «Cargando…» y sin filtros).
  for (const faltante of ['accionesControlHoras', 'formFiltrosHoras', 'panelRegistroManual', 'formRegistroManual', 'tablaRegistros', 'alcanceResumen']) {
    reiniciar(); ctx.__usuario = usuario; ausentes.add(faltante);
    const principal = crear('main'); ctx.document.querySelector = tag => tag === 'main' ? principal : crear('qs');
    await manejadores.DOMContentLoaded();
    assert.strictEqual(llamadas.length, 0, `con «${faltante}» ausente no se consulta la API`);
    const aviso = principal.children[0];
    assert.strictEqual(aviso.className, 'mensaje error', faltante);
    assert.strictEqual(aviso.atributos.role, 'alert');
    assert.ok(aviso.children[0].textContent.includes('versión anterior de esta pantalla'));
    const boton = aviso.children[1];
    assert.strictEqual(boton.textContent, 'Recargar página');
    let recargas = 0; ctx.window.location.reload = () => { recargas += 1; };
    boton.eventos.click();
    assert.strictEqual(recargas, 1, 'el botón recarga la página');
  }
  console.log('OK');
})().catch(error => { console.error(error); process.exit(1); });
"""


@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
def test_control_de_horas_preselecciona_la_tarea_del_detalle_y_avisa_si_el_html_es_anterior():
    ejecutar_node(("frontend", "control_horas", "control_horas.js"), GUION_CONTROL)
