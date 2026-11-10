"""Interfaz de D1 (aviso y confirmación de duración, sin dobles envíos) y D2 (anulación del administrador).

Comprobaciones estáticas y de lógica con Node; el recorrido en navegador sigue pendiente (ver 07).
"""
import json
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(RAIZ, "frontend", "control_horas", "control_horas.js"), encoding="utf-8").read()
HTML = open(os.path.join(RAIZ, "frontend", "control_horas", "control_horas.html"), encoding="utf-8").read()


def test_el_html_trae_el_aviso_y_el_dialogo_de_anulacion_con_motivo_obligatorio():
    assert 'id="avisoDuracionTemporizador"' in HTML
    assert '<dialog id="dialogoAnularRegistro"' in HTML
    assert re.search(r'<textarea id="motivoAnulacion"[^>]*maxlength="255"[^>]*required', HTML)
    assert "no guarda si estas horas ya fueron" in HTML  # D3: avisa que no hay dato de facturación


def test_detener_solo_envia_cuerpo_al_confirmar_y_maneja_la_duracion_anomala():
    assert '"DURACION_ANOMALA"' in JS and "confirmar_duracion: true" in JS
    assert 'confirmarAccion(' in JS
    # Sin confirmar, la petición sigue sin cuerpo ni Content-Type (el backend valida todo cuerpo JSON).
    assert JS.count('"Content-Type": "application/json"') >= 3
    # El clic no arrastra el evento como si fuera una confirmación: solo `duracionConfirmada` la activa.
    assert 'btnDetener.addEventListener("click", detenerTemporizador);' in JS
    assert "const confirmarDuracion = duracionConfirmada;" in JS and "duracionConfirmada = true;" in JS


def test_iniciar_y_detener_comparten_una_guarda_contra_dobles_envios():
    assert len(re.findall(r"if \(solicitudEnCurso", JS)) >= 3  # iniciar, detener y anular
    assert JS.count("solicitudEnCurso = false;") >= 3


def test_el_historial_del_administrador_pide_los_anulados_y_el_resto_no():
    assert 'parametros.set("incluir_anulados", "1")' in JS
    bloque = JS[JS.index('parametros.set("incluir_anulados"') - 120:JS.index('parametros.set("incluir_anulados"')]
    assert 'usuarioActual.nombre_rol === "ADMINISTRADOR"' in bloque


def test_el_boton_anular_solo_se_crea_para_el_administrador_y_los_anulados_no_lo_tienen():
    celda = JS[JS.index("function agregarCeldaOrigen"):JS.index("function renderizarResumen")]
    assert 'registro.estado_registro === "ANULADO"' in celda
    assert 'else if (usuarioActual && usuarioActual.nombre_rol === "ADMINISTRADOR")' in celda
    assert 'btn-anular-registro' in celda


@pytest.mark.skipif(not shutil.which("node"), reason="Node no disponible")
@pytest.mark.parametrize("umbral,segundos,visible", [(12, 13 * 3600, True), (12, 11 * 3600, False), (None, 99 * 3600, False)])
def test_el_aviso_de_duracion_aparece_solo_sobre_el_umbral(umbral, segundos, visible):
    m = re.search(r"function actualizarAvisoDuracion\(segundos\) \{.*?\n\}\n", JS, re.S)
    assert m
    codigo = f"""
    let umbralAvisoHoras = {json.dumps(umbral)};
    const aviso = {{ hidden: true, textContent: '' }};
    const document = {{ getElementById: () => aviso }};
    {m.group(0)}
    actualizarAvisoDuracion({segundos});
    console.log(JSON.stringify({{ hidden: aviso.hidden, texto: aviso.textContent }}));
    """
    salida = json.loads(subprocess.run(["node", "-e", codigo], capture_output=True, text=True, check=True).stdout)
    assert salida["hidden"] is (not visible)
    if visible:
        assert "horas en curso" in salida["texto"]


def test_si_otra_pestana_ya_detuvo_el_temporizador_la_pantalla_se_resincroniza():
    bloque = JS[JS.index("async function detenerTemporizador()"):JS.index("function activarTemporizador(")]
    corte = bloque[bloque.index("if (!response.ok) {"):]
    assert "response.status === 404" in corte[:400]
    assert corte.index("await cargarContexto();") < corte.index("return;")
    assert "await cargarRegistros();" in corte[:600]


def test_tras_anular_el_foco_pasa_a_un_destino_que_existe():
    bloque = JS[JS.index("async function enviarAnulacion"):]
    exito = bloque[bloque.index('document.getElementById("dialogoAnularRegistro").close();'):]
    assert "await cargarRegistros();" in exito[:200]
    assert 'mensajeControl.setAttribute("tabindex", "-1");' in exito and "mensajeControl.focus();" in exito
