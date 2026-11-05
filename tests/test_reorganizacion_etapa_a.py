import json
import os
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="requiere Node.js")
def test_panel_alta_abre_cierra_mueve_el_foco_y_ignora_ids_inexistentes():
    ruta = os.path.join(RAIZ, "frontend", "assets", "js", "panel_alta.js")
    guion = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const elementos = new Map();
function crearElemento() {
  return {
    hidden: false,
    atributos: {},
    eventos: {},
    foco: 0,
    desplazamientos: [],
    setAttribute(nombre, valor) { this.atributos[nombre] = valor; },
    getAttribute(nombre) { return this.atributos[nombre] || null; },
    addEventListener(nombre, callback) { this.eventos[nombre] = callback; },
    focus() { this.foco += 1; },
    scrollIntoView(opciones) { this.desplazamientos.push(opciones); }
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
assert.strictEqual(JSON.stringify(panel.desplazamientos), '[{"block":"nearest"}]');
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
