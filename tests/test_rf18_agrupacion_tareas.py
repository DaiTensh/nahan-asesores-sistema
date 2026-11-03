# -*- coding: utf-8 -*-
"""RF18 — Visualizando Tareas Pendientes, agrupadas por cliente, prioridad y responsable.

El texto oficial pide ver todas las tareas pendientes «agrupadas por cliente, prioridad
y usuario responsable». El listado ya filtraba por estado (RF69) y por responsable
(RF68); faltaba agrupar. La agrupación es una función pura del navegador
(frontend/assets/js/agrupar_tareas.js) sobre la lista ya cargada: no hace consultas
nuevas. Aquí se prueba con Node y, de punta a punta, con la API contra un MySQL real.
"""
import json
import os
import shutil
import subprocess

import pytest

from tests.mysql_desechable import BASE_APP, herramientas_disponibles
from tests.test_rf74_mysql_real import mundo, servidor  # noqa: F401  (fixtures compartidas)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
requiere_node = pytest.mark.skipif(NODE is None, reason="requiere Node.js")
requiere_mysql = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)


def agrupar_en_el_navegador(tareas, criterio):
    guion = (
        "global.window = {}; require(process.argv[1]);"
        "const [tareas, criterio] = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "console.log(JSON.stringify(window.AgruparTareas.agrupar(tareas, criterio)));"
    )
    salida = subprocess.run([NODE, "-e", guion, os.path.join(RAIZ, "frontend", "assets", "js", "agrupar_tareas.js")],
                            input=json.dumps([tareas, criterio]), capture_output=True, text=True, timeout=30, check=True).stdout
    return json.loads(salida)


def tarea(id_tarea, cliente, id_cliente, prioridad, responsable, id_responsable):
    return {"id_tarea": id_tarea, "cliente": cliente, "id_cliente": id_cliente, "prioridad": prioridad,
            "responsable": responsable, "id_responsable": id_responsable}


MUESTRA = [
    tarea(1, "Zeta Ltda.", 3, "BAJA", "Carlos Castro", 7),
    tarea(2, "Álamos SpA", 1, "URGENTE", "Elías Alarcón", 4),
    tarea(3, "Zeta Ltda.", 3, "ALTA", "Carlos Castro", 7),
    tarea(4, "Beta SpA", 2, "URGENTE", "Carlos Castro", 7),
    tarea(5, "Álamos SpA", 1, "MEDIA", "Elías Alarcón", 4),
]


@requiere_node
def test_agrupa_por_cliente_en_orden_alfabetico_y_conserva_el_orden_de_llegada():
    grupos = agrupar_en_el_navegador(MUESTRA, "cliente")

    assert [g["etiqueta"] for g in grupos] == ["Álamos SpA", "Beta SpA", "Zeta Ltda."], "«Á» se ordena con la «A», no al final"
    assert [[t["id_tarea"] for t in g["tareas"]] for g in grupos] == [[2, 5], [4], [1, 3]]


@requiere_node
def test_agrupa_por_prioridad_de_mas_a_menos_urgente():
    grupos = agrupar_en_el_navegador(MUESTRA, "prioridad")

    assert [g["etiqueta"] for g in grupos] == ["Urgente", "Alta", "Media", "Baja"]
    assert [len(g["tareas"]) for g in grupos] == [2, 1, 1, 1]


@requiere_node
def test_agrupa_por_responsable():
    grupos = agrupar_en_el_navegador(MUESTRA, "responsable")

    assert [(g["etiqueta"], [t["id_tarea"] for t in g["tareas"]]) for g in grupos] == [
        ("Carlos Castro", [1, 3, 4]), ("Elías Alarcón", [2, 5])]


@requiere_node
def test_dos_clientes_con_la_misma_razon_social_no_se_fusionan():
    homonimos = [tarea(1, "Comercial Andes", 10, "ALTA", "A", 1), tarea(2, "Comercial Andes", 11, "ALTA", "A", 1)]

    assert [len(g["tareas"]) for g in agrupar_en_el_navegador(homonimos, "cliente")] == [1, 1]


@requiere_node
@pytest.mark.parametrize("criterio", ["", "area", "estado", None, "CLIENTE"])
def test_sin_un_criterio_valido_devuelve_un_solo_grupo_con_todo(criterio):
    grupos = agrupar_en_el_navegador(MUESTRA, criterio)

    assert len(grupos) == 1 and [t["id_tarea"] for t in grupos[0]["tareas"]] == [1, 2, 3, 4, 5]


@requiere_node
def test_una_lista_vacia_no_produce_grupos():
    assert agrupar_en_el_navegador([], "cliente") == []


@requiere_node
def test_una_prioridad_desconocida_va_al_final_sin_perder_la_tarea():
    grupos = agrupar_en_el_navegador(MUESTRA + [tarea(6, "X", 9, "RARA", "A", 1)], "prioridad")

    assert grupos[-1]["clave"] == "RARA" and len(grupos[-1]["tareas"]) == 1


# ---------------------------------------------------------------------------
# De punta a punta: la API real y la agrupación del navegador
# ---------------------------------------------------------------------------

@requiere_mysql
@requiere_node
@pytest.mark.parametrize("criterio,campo", [("cliente", "id_cliente"), ("prioridad", "prioridad"), ("responsable", "id_responsable")])
def test_los_grupos_de_la_lista_real_cuadran_con_el_total_y_son_homogeneos(client, iniciar_sesion, mundo, servidor, criterio, campo):  # noqa: F811
    cn = servidor.conectar(base=BASE_APP)
    cur = cn.cursor()
    for titulo, cliente, prioridad, responsable in [("T2", 2, "URGENTE", 2), ("T3", 1, "BAJA", 1), ("T4", 2, "ALTA", 2), ("T5", 1, "URGENTE", 1)]:
        cur.execute(
            "INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, prioridad, fecha_vencimiento) "
            "VALUES (%s, 1, %s, 1, %s, %s, '2026-12-31')", (cliente, responsable, titulo, prioridad))
    cn.commit()
    cn.close()
    iniciar_sesion(usuario_id=1, rol_id=1)

    lista = client.get("/api/tareas/pendientes").get_json()
    grupos = agrupar_en_el_navegador(lista, criterio)

    assert len(lista) == 5 and "id_cliente" in lista[0], "la API entrega el id del cliente para no fusionar homónimos"
    assert sum(len(g["tareas"]) for g in grupos) == len(lista)
    assert sorted(t["id_tarea"] for g in grupos for t in g["tareas"]) == sorted(t["id_tarea"] for t in lista)
    for grupo in grupos:
        assert len({str(t[campo]) for t in grupo["tareas"]}) == 1


# ---------------------------------------------------------------------------
# Pantalla
# ---------------------------------------------------------------------------

def _leer(*partes):
    with open(os.path.join(RAIZ, "frontend", *partes), encoding="utf-8") as archivo:
        return archivo.read()


def test_la_pantalla_ofrece_los_tres_criterios_y_carga_el_modulo_antes_que_su_script():
    html = _leer("tareas", "tareas.html")
    selector = html[html.index('id="agruparPor"'):html.index("</select>", html.index('id="agruparPor"'))]
    assert all(f'value="{c}"' in selector for c in ("", "cliente", "prioridad", "responsable"))
    assert html.index("agrupar_tareas.js") < html.index("./tareas.js")


def test_agrupar_no_hace_consultas_nuevas_ni_inserta_html():
    js = _leer("tareas", "tareas.js")
    manejador = js[js.index('getElementById("agruparPor")'):js.index('getElementById("filtroEstado")')]
    assert "fetch(" not in manejador and "cargarTareasPendientes" not in manejador, "se vuelve a dibujar desde la lista ya cargada"
    funcion = js[js.index("function crearFilaGrupo"):js.index("function alternarSeleccionarTodas")]
    assert "innerHTML" not in funcion and 'scope = "colgroup"' in funcion
    assert "innerHTML" not in _leer("assets", "js", "agrupar_tareas.js")
