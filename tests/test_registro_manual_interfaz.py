"""Interfaz del registro manual de horas (Control de horas).

Parte estática (estructura, orden de scripts, accesibilidad básica) y parte de
comportamiento: se ejecuta control_horas.js con Node y un DOM mínimo simulado
para comprobar las validaciones del navegador, la confirmación previa y el
cuerpo exacto de la solicitud. El servidor vuelve a validar todo; esto solo
verifica que la pantalla avise rápido y no envíe nada indebido.
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


HTML = leer("frontend", "control_horas", "control_horas.html")
JS = leer("frontend", "control_horas", "control_horas.js")


def test_el_panel_tiene_los_campos_obligatorios_y_etiquetas_asociadas():
    panel = re.search(r'<section[^>]*id="panelRegistroManual"[^>]*>(.*?)</section>', HTML, re.S).group(1)

    assert 'id="panelRegistroManual" hidden' in HTML
    assert 'aria-labelledby="tituloRegistroManual"' in HTML and 'id="tituloRegistroManual"' in panel
    for id_campo, tipo in (
        ("rmCliente", "select"), ("rmTarea", "select"), ("rmFecha", 'input id="rmFecha" class="form-input" type="date"'),
        ("rmHoraInicio", 'type="time"'), ("rmHoraFin", 'type="time"'), ("rmObservacion", "textarea"),
    ):
        assert f'for="{id_campo}"' in panel, f"falta la etiqueta de {id_campo}"
        assert f'id="{id_campo}"' in panel
        assert "required" in re.search(rf'<[^>]*id="{id_campo}"[^>]*>', panel).group(0)
    assert 'maxlength="255"' in panel, "el mismo largo que la columna observacion"
    assert 'type="submit" id="btnGuardarRegistroManual"' in panel
    assert 'id="btnCancelarRegistroManual"' in panel and 'type="button" id="btnCancelarRegistroManual"' in panel
    assert 'id="rmDuracion" class="registro-manual-duracion" aria-live="polite"' in panel
    assert 'id="mensajeRegistroManual" class="mensaje" aria-live="polite"' in panel
    assert "innerHTML" not in JS


def test_el_boton_se_crea_para_todos_los_roles_junto_a_los_existentes_y_abre_el_panel():
    assert 'id="accionesControlHoras" hidden' in HTML
    assert HTML.index('id="accionesControlHoras"') < HTML.index('id="panelRegistroManual"') < HTML.index('class="time-shell"')

    creacion = JS.index('botonRegistroManual.id = "btnRegistroManual"')
    bloque_admin = JS.index('if (usuarioActual.nombre_rol === "ADMINISTRADOR") {')
    assert creacion < bloque_admin, "el botón no depende del rol"
    assert JS.index("accionesControlHoras.appendChild(botonRegistroManual)") < bloque_admin, \
        "y tampoco su inserción en la barra de acciones"
    assert 'botonRegistroManual.textContent = "Registrar horas manualmente"' in JS
    assert 'botonRegistroManual.type = "button"' in JS
    assert JS.index("configurarRegistroManual();") > JS.index("accionesControlHoras.hidden = false")
    assert HTML.index("../assets/js/panel_alta.js") < HTML.index("./control_horas.js")
    for fragmento in ('botonId: "btnRegistroManual"', 'panelId: "panelRegistroManual"',
                      'primerCampoId: "rmCliente"', 'botonCerrarId: "btnCancelarRegistroManual"'):
        assert fragmento in JS


def test_el_historial_tiene_la_columna_origen_con_insignia_y_la_observacion_como_texto():
    assert "<th>Origen</th>" in HTML
    assert 'colspan="9" class="text-loading"' in HTML
    assert 'colSpan = esAdministrador ? 10 : 9' in JS and 'ADMINISTRADOR" ? 10 : 9' in JS
    celda = JS[JS.index("function agregarCeldaOrigen"):JS.index("function renderizarResumen")]
    assert '"Manual"' in celda and '"Temporizador"' in celda
    assert "observacion.textContent = registro.observacion" in celda


def test_la_confirmacion_precede_al_envio_y_la_solicitud_lleva_cuerpo_json():
    funcion = JS[JS.index("async function enviarRegistroManual"):JS.index("async function refrescarHistorialTrasRegistro")]

    assert funcion.index("await confirmarAccion(") < funcion.index("await fetch(")
    assert "no se pueden editar ni anular" in funcion
    assert '`${API_URL}/control-horas/registros-manuales`' in funcion
    assert 'method: "POST"' in funcion and '"Content-Type": "application/json"' in funcion
    assert "body: JSON.stringify(lectura.datos)" in funcion
    assert "setBotonCargando(boton, true" in funcion and "finally" in funcion, "evita el doble envío"


def test_el_plazo_del_navegador_coincide_con_el_del_servidor():
    from backend.routes import control_horas_routes

    dias = int(re.search(r"const DIAS_MAXIMOS_RETROACTIVO = (\d+);", JS).group(1))
    assert dias == control_horas_routes.DIAS_MAXIMOS_RETROACTIVO
    assert f"maxlength=\"{control_horas_routes.LARGO_MAXIMO_OBSERVACION}\"" in HTML


def test_los_estilos_del_panel_se_adaptan_a_pantallas_angostas():
    css = leer("frontend", "control_horas", "control_horas.css")

    assert ".registro-manual-grid" in css
    assert re.search(r"@media \(max-width: 900px\)\s*\{[^@]*\.registro-manual-grid\s*\{\s*grid-template-columns: repeat\(2", css, re.S)
    assert re.search(r"@media \(max-width: 540px\)\s*\{[^@]*\.registro-manual-grid\s*\{\s*grid-template-columns: 1fr", css, re.S)
    assert "scroll-margin-top: 168px" in css[css.index("#panelRegistroManual"):css.index("#panelRegistroManual") + 120]
    assert "overflow-wrap: anywhere" in css[css.index(".origen-observacion"):css.index(".origen-observacion") + 200]


GUION_NODE = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
process.on('unhandledRejection', error => { console.error('RECHAZO SIN ATENDER', error); process.exit(3); });

const elementos = {};
function crear(id) {
  let texto = '';
  const elemento = {
    id, value: '', className: '', hidden: false, disabled: false, max: '', min: '',
    focusCount: 0, children: [], selectedOptions: [{ textContent: '' }],
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    addEventListener() {}, setAttribute() {}, getAttribute: () => null, reset() {},
    appendChild(hijo) { this.children.push(hijo); return hijo; },
    focus() { this.focusCount += 1; }
  };
  // Como en un navegador, asignar textContent reemplaza (vacía) a los hijos.
  Object.defineProperty(elemento, 'textContent', {
    get: () => texto,
    set: valor => { texto = valor; elemento.children.length = 0; }
  });
  return elemento;
}
const obtener = id => (elementos[id] = elementos[id] || crear(id));
const llamadas = { fetch: [], confirmar: [], avisos: [], cierres: 0 };
const estado = { acepta: true, respuesta: null };

const ctx = vm.createContext({
  document: { getElementById: obtener, createElement: () => crear('nuevo'), addEventListener() {},
              querySelector: () => crear('qs'), currentScript: null },
  window: { API_CONFIG: { API_URL: '/api', credentials: 'include' }, location: {} },
  console, URLSearchParams, Intl, Date, Math, Number, String, JSON, Map, Array, Promise, setTimeout,
  setInterval: () => 0, clearInterval() {},
  fetch: async (url, opciones) => {
    llamadas.fetch.push({ url, opciones });
    if (url.endsWith('/control-horas/registros-manuales')) return estado.respuesta;
    const cuerpo = url.includes('/filtros') ? { clientes: [], tareas: [], usuarios: [] }
                                            : { registros: [], resumen: {} };
    return { ok: true, status: 200, text: async () => JSON.stringify(cuerpo) };
  },
  confirmarAccion: async (mensaje, nivel) => { llamadas.confirmar.push({ mensaje, nivel }); return estado.acepta; },
  avisarAccion: async (mensaje, tipo) => { llamadas.avisos.push({ mensaje, tipo }); },
  configurarPanelAlta: () => ({ abrir() {}, cerrar() { llamadas.cierres += 1; }, estaAbierto: () => true }),
  formatearFechaHora24: valor => valor
});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const ejecutar = codigo => vm.runInContext(codigo, ctx);

const pad = n => String(n).padStart(2, '0');
const local = f => `${f.getFullYear()}-${pad(f.getMonth() + 1)}-${pad(f.getDate())}`;
const hoy = new Date();
const dias = n => { const f = new Date(hoy); f.setDate(f.getDate() + n); return local(f); };

ejecutar(`
  usuarioActual = { nombre_rol: 'USUARIO_AREA_JURIDICA' };
  tareasDisponibles = [
    { id_tarea: 11, id_cliente: 7, titulo: 'Declaración mensual', descripcion: '', cliente: 'Cliente Uno', cliente_rut: '11.111.111-1' },
    { id_tarea: 12, id_cliente: 7, titulo: 'Balance', descripcion: '', cliente: 'Cliente Uno', cliente_rut: '11.111.111-1' },
    { id_tarea: 21, id_cliente: 8, titulo: 'Contrato', descripcion: '', cliente: 'Cliente Dos', cliente_rut: '22.222.222-2' }
  ];
  clientesDisponibles = obtenerClientesDesdeTareas(tareasDisponibles);
  panelRegistroManual = configurarPanelAlta({});
`);

(async () => {
  // --- Apertura: clientes, tareas, fecha por defecto y límites del campo de fecha.
  ejecutar('prepararRegistroManual()');
  assert.strictEqual(obtener('rmCliente').children.length, 3, 'placeholder + 2 clientes');
  assert.strictEqual(obtener('rmFecha').value, dias(0));
  assert.strictEqual(obtener('rmFecha').max, dias(0));
  assert.strictEqual(obtener('rmFecha').min, dias(-30));
  assert.strictEqual(obtener('rmTarea').disabled, true, 'la tarea espera al cliente');
  assert.strictEqual(obtener('btnGuardarRegistroManual').disabled, false);

  obtener('rmCliente').value = '7';
  ejecutar('poblarTareasRegistroManual()');
  assert.strictEqual(obtener('rmTarea').children.length, 3, 'placeholder + 2 tareas del cliente 7');
  assert.strictEqual(obtener('rmTarea').disabled, false);
  obtener('rmCliente').value = '';
  ejecutar('poblarTareasRegistroManual()');
  assert.strictEqual(obtener('rmTarea').disabled, true);

  // --- Sin tareas habilitadas: no se puede enviar.
  ejecutar('const tareasGuardadas = tareasDisponibles; tareasDisponibles = []; clientesDisponibles = []; prepararRegistroManual();');
  assert.strictEqual(obtener('btnGuardarRegistroManual').disabled, true);
  assert.ok(obtener('mensajeRegistroManual').textContent.includes('No tiene tareas habilitadas'));
  ejecutar('tareasDisponibles = tareasGuardadas; clientesDisponibles = obtenerClientesDesdeTareas(tareasDisponibles);');

  // --- Vista previa de la duración.
  const duracion = (inicio, fin) => {
    obtener('rmHoraInicio').value = inicio; obtener('rmHoraFin').value = fin;
    ejecutar('actualizarDuracionRegistroManual()');
    return obtener('rmDuracion').textContent;
  };
  assert.strictEqual(duracion('09:00', '11:30'), '2 h 30 min');
  assert.strictEqual(duracion('09:00', '09:05'), '0 h 05 min');
  assert.strictEqual(duracion('00:00', '23:59'), '23 h 59 min');
  assert.ok(duracion('11:00', '10:00').includes('posterior'));
  assert.ok(duracion('11:00', '11:00').includes('posterior'));
  assert.ok(duracion('', '11:00').includes('Indique'));

  // --- Validaciones del navegador (cada una enfoca el campo con el problema).
  function formulario(cambios) {
    const base = { rmCliente: '7', rmTarea: '11', rmFecha: dias(-1), rmHoraInicio: '09:00', rmHoraFin: '11:30',
                   rmObservacion: 'Visita a terreno' };
    Object.assign(base, cambios);
    for (const [id, valor] of Object.entries(base)) obtener(id).value = valor;
  }
  const casos = [
    [{ rmCliente: '' }, 'rmCliente', 'cliente'],
    [{ rmTarea: '' }, 'rmTarea', 'tarea'],
    [{ rmFecha: '' }, 'rmFecha', 'fecha'],
    [{ rmFecha: dias(1) }, 'rmFecha', 'todavía no ocurrieron'],
    [{ rmFecha: dias(-31) }, 'rmFecha', 'últimos 30 días'],
    [{ rmHoraInicio: '' }, 'rmHoraInicio', 'hora de inicio'],
    [{ rmHoraFin: '' }, 'rmHoraFin', 'hora de término'],
    [{ rmHoraFin: '08:00' }, 'rmHoraFin', 'posterior'],
    [{ rmHoraFin: '09:00' }, 'rmHoraFin', 'posterior'],
    [{ rmObservacion: '   ' }, 'rmObservacion', 'observación'],
  ];
  for (const [cambio, campo, texto] of casos) {
    formulario(cambio);
    const antes = obtener(campo).focusCount;
    const lectura = ejecutar('leerRegistroManual()');
    assert.ok(lectura.error && lectura.error.toLowerCase().includes(texto.toLowerCase()), JSON.stringify([cambio, lectura.error]));
    assert.strictEqual(lectura.campo.id, campo, 'el campo señalado');
    assert.strictEqual(lectura.datos, undefined);
    ejecutar('enviarRegistroManual({ preventDefault() {} })');
    await new Promise(r => setTimeout(r, 0));
    assert.strictEqual(obtener(campo).focusCount, antes + 1, `enfoca ${campo}`);
    assert.strictEqual(obtener('mensajeRegistroManual').className, 'mensaje error');
  }
  assert.strictEqual(llamadas.confirmar.length, 0, 'con datos inválidos no se pide confirmar');
  assert.strictEqual(llamadas.fetch.length, 0, 'con datos inválidos no se envía nada');

  // Límite exacto del plazo y observación con espacios alrededor.
  formulario({ rmFecha: dias(-30), rmObservacion: '  Reunión con el cliente  ' });
  let lectura = ejecutar('leerRegistroManual()');
  assert.deepStrictEqual(JSON.parse(JSON.stringify(lectura.datos)), {
    id_tarea: 11, fecha: dias(-30), hora_inicio: '09:00', hora_fin: '11:30', observacion: 'Reunión con el cliente' });
  assert.strictEqual(lectura.minutos, 150);

  // --- Cancelar la confirmación: no se envía.
  formulario({});
  estado.acepta = false;
  await ejecutar('enviarRegistroManual({ preventDefault() {} })');
  assert.strictEqual(llamadas.confirmar.length, 1);
  assert.strictEqual(llamadas.fetch.length, 0);
  const confirmacion = llamadas.confirmar[0];
  assert.strictEqual(confirmacion.nivel, 'advertencia');
  for (const texto of ['02h 30m', 'Declaración mensual', 'Cliente Uno', '09:00 a 11:30', 'no se pueden editar ni anular']) {
    assert.ok(confirmacion.mensaje.includes(texto), `la confirmación dice «${texto}»: ${confirmacion.mensaje}`);
  }
  assert.ok(confirmacion.mensaje.includes(`${dias(-1).split('-').reverse().join('-')}`), 'fecha dd-mm-aaaa');

  // --- Éxito: cuerpo exacto, aviso con duración y monto, panel cerrado.
  estado.acepta = true;
  estado.respuesta = { ok: true, status: 201, text: async () => JSON.stringify({
    message: 'Horas registradas manualmente correctamente.',
    registro: { duracion_minutos: 150, monto: 75000 }, resumen: {} }) };
  await ejecutar('enviarRegistroManual({ preventDefault() {} })');
  const envio = llamadas.fetch.find(f => f.url.endsWith('/registros-manuales'));
  assert.strictEqual(envio.url, '/api/control-horas/registros-manuales');
  assert.strictEqual(envio.opciones.method, 'POST');
  assert.strictEqual(envio.opciones.headers['Content-Type'], 'application/json');
  assert.deepStrictEqual(JSON.parse(envio.opciones.body), {
    id_tarea: 11, fecha: dias(-1), hora_inicio: '09:00', hora_fin: '11:30', observacion: 'Visita a terreno' });
  assert.strictEqual(llamadas.cierres, 1, 'se cierra el panel');
  assert.strictEqual(llamadas.avisos.length, 1);
  assert.strictEqual(llamadas.avisos[0].tipo, 'exito');
  assert.ok(llamadas.avisos[0].mensaje.includes('02h 30m') && llamadas.avisos[0].mensaje.includes('75.000'));
  assert.strictEqual(obtener('btnGuardarRegistroManual').textContent, 'Registrar horas');
  assert.strictEqual(obtener('btnGuardarRegistroManual').disabled, false);
  await new Promise(r => setTimeout(r, 20));
  assert.ok(llamadas.fetch.some(f => f.url.includes('/control-horas/filtros')), 'refresca los filtros');
  assert.ok(llamadas.fetch.some(f => f.url.includes('/control-horas/registros?') || f.url.endsWith('/control-horas/registros')), 'refresca el historial');

  // --- Rechazo del servidor (409): mensaje en el panel, sin cerrar ni avisar.
  const cierres = llamadas.cierres, avisos = llamadas.avisos.length;
  formulario({});
  estado.respuesta = { ok: false, status: 409, text: async () => JSON.stringify({ error: 'Ese horario se superpone con horas que ya registró.' }) };
  await ejecutar('enviarRegistroManual({ preventDefault() {} })');
  assert.strictEqual(obtener('mensajeRegistroManual').textContent, 'Ese horario se superpone con horas que ya registró.');
  assert.strictEqual(obtener('mensajeRegistroManual').className, 'mensaje error');
  assert.strictEqual(llamadas.cierres, cierres);
  assert.strictEqual(llamadas.avisos.length, avisos);
  assert.strictEqual(obtener('btnGuardarRegistroManual').disabled, false, 'se puede corregir y reintentar');

  // --- Sin conexión: mensaje claro y botón disponible.
  estado.respuesta = null;
  llamadas.fetch.length = 0;
  ctx.fetch = async () => { throw new Error('sin red'); };
  formulario({});
  const consola = console.error; console.error = () => {};
  await ejecutar('enviarRegistroManual({ preventDefault() {} })');
  console.error = consola;
  assert.strictEqual(obtener('mensajeRegistroManual').textContent, 'No se pudo conectar con el servidor.');
  assert.strictEqual(obtener('btnGuardarRegistroManual').disabled, false);

  // --- Historial: la insignia distingue el origen y la observación es texto.
  const filas = [];
  ctx.document.createElement = () => crear('nuevo');
  const fila = crear('fila');
  ejecutar(`agregarCeldaOrigen`);
  vm.runInContext('globalThis.__f = agregarCeldaOrigen', ctx);
  ctx.__f(fila, { origen: 'MANUAL', observacion: '<img src=x onerror=alert(1)>' });
  ctx.__f(fila, { origen: 'TEMPORIZADOR', observacion: null });
  const [manual, temporizador] = fila.children;
  assert.strictEqual(manual.children[0].textContent, 'Manual');
  assert.strictEqual(manual.children[1].textContent, '<img src=x onerror=alert(1)>', 'se muestra como texto');
  assert.strictEqual(temporizador.children[0].textContent, 'Temporizador');
  assert.strictEqual(temporizador.children.length, 1);
  console.log('OK');
})().catch(error => { console.error(error); process.exit(1); });
"""


@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
def test_comportamiento_del_formulario_con_un_dom_simulado():
    ruta = os.path.join(RAIZ, "frontend", "control_horas", "control_horas.js")

    resultado = subprocess.run(
        [NODE, "-e", GUION_NODE, ruta], capture_output=True, text=True, timeout=60, cwd=RAIZ
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert resultado.stdout.strip().endswith("OK")


def test_reportes_atiende_el_rechazo_de_la_carga_de_catalogos_de_horas():
    """cargarCatalogosHoras relanza el error tras avisarlo; su única llamada no debe dejarlo sin atender."""
    reportes = leer("frontend", "reportes", "reportes.js")

    assert "throw error;" in reportes[reportes.index("async function cargarCatalogosHoras"):]
    assert "if (esHoras) cargarCatalogosHoras().catch(() => {});" in reportes
    assert len(re.findall(r"cargarCatalogosHoras\(", reportes)) == 2, "la definición y una sola llamada"
