# -*- coding: utf-8 -*-
"""Regresiones de la auditoría de cierre del Incremento 4 que viven en la interfaz.

El código de la interfaz es JavaScript sin framework y estas pruebas corren sin navegador: fijan en el
código fuente lo que se comprobó en Chrome durante la auditoría (menú con scroll, textos y formatos).
Las que dependen del backend (fechas de usuarios y clientes, avisos) están junto a las de su módulo.
"""
import os

from backend.utils.estados_tarea import etiqueta_estado

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
