# -*- coding: utf-8 -*-
"""AUD-033: las transiciones de una tarea bloquean su fila al leerla.

Sin el bloqueo, dos personas que actúan a la vez sobre la misma tarea leen el mismo estado, ambas lo
dan por válido y la última escritura pisa a la primera. Con `SELECT … FOR UPDATE` la segunda espera y
valida contra el estado ya cambiado. La prueba es determinista: una transacción ajena retiene la fila,
la solicitud debe quedar esperando y, al liberarla, decidir con el estado nuevo.
"""
import os
import threading

import pytest

from tests.mysql_desechable import BASE_APP, herramientas_disponibles
from tests.test_rf74_mysql_real import mundo, servidor  # noqa: F401  (fixtures compartidas)

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)

ID_ADMIN, ID_JURIDICA = 1, 2


@pytest.fixture
def tarea_ajena_bloqueada(servidor, mundo):  # noqa: F811
    """Crea una tarea del usuario 2 y devuelve (id, conexión que la tiene bloqueada, cursor)."""
    cn = servidor.conectar(base=BASE_APP)
    cur = cn.cursor()
    cur.execute("INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, estado) "
                "VALUES (1, 1, %s, 1, 'Tarea concurrente', 'PENDIENTE')", (ID_JURIDICA,))
    cn.commit()
    id_tarea = cur.lastrowid
    cn2 = servidor.conectar(base=BASE_APP)
    cur2 = cn2.cursor()
    cn2.start_transaction()
    cur2.execute("SELECT estado FROM tarea WHERE id_tarea = %s FOR UPDATE", (id_tarea,))
    cur2.fetchall()
    yield id_tarea, cn2, cur2
    cn2.rollback()
    cn2.close()
    cn.close()


def _en_hilo(funcion):
    resultado = {}
    hilo = threading.Thread(target=lambda: resultado.update(respuesta=funcion()))
    hilo.start()
    return hilo, resultado


def test_el_cambio_de_estado_espera_a_la_otra_transaccion_y_valida_contra_el_estado_nuevo(
        client, iniciar_sesion, mundo, tarea_ajena_bloqueada):  # noqa: F811
    id_tarea, otra, cursor_otra = tarea_ajena_bloqueada
    iniciar_sesion(usuario_id=ID_JURIDICA, rol_id=2, area_id=1)

    hilo, resultado = _en_hilo(lambda: client.put(f"/api/tareas/{id_tarea}/estado", json={"estado": "EN_PROCESO"}))
    hilo.join(1.0)
    assert hilo.is_alive(), "la solicitud debe esperar mientras otra transacción tiene la tarea"

    cursor_otra.execute("UPDATE tarea SET estado = 'PAUSADA' WHERE id_tarea = %s", (id_tarea,))
    otra.commit()
    hilo.join(15)

    assert not hilo.is_alive() and resultado["respuesta"].status_code == 200
    evento = mundo.consulta("SELECT datos_anteriores, datos_nuevos FROM auditoria WHERE accion = 'CAMBIO_ESTADO_TAREA'")[0]
    assert "estado=PAUSADA" in evento["datos_anteriores"] and "estado=EN_PROCESO" in evento["datos_nuevos"], \
        "decidió con el estado ya cambiado (PAUSADA), no con el que leyó al llegar (PENDIENTE)"


def test_si_la_otra_transaccion_finalizo_la_tarea_el_cambio_se_rechaza(
        client, iniciar_sesion, mundo, tarea_ajena_bloqueada):  # noqa: F811
    id_tarea, otra, cursor_otra = tarea_ajena_bloqueada
    iniciar_sesion(usuario_id=ID_JURIDICA, rol_id=2, area_id=1)

    hilo, resultado = _en_hilo(lambda: client.put(f"/api/tareas/{id_tarea}/estado", json={"estado": "EN_PROCESO"}))
    hilo.join(1.0)
    assert hilo.is_alive()

    cursor_otra.execute("UPDATE tarea SET estado = 'COMPLETADA' WHERE id_tarea = %s", (id_tarea,))
    otra.commit()
    hilo.join(15)

    assert resultado["respuesta"].status_code == 409, "una tarea finalizada no vuelve a abrirse por una solicitud en carrera"
    assert mundo.consulta("SELECT estado FROM tarea WHERE id_tarea = %s", (id_tarea,))[0]["estado"] == "COMPLETADA"
    assert not mundo.consulta("SELECT 1 FROM auditoria WHERE accion = 'CAMBIO_ESTADO_TAREA'")


def test_el_cambio_de_prioridad_tambien_espera_la_fila(client, iniciar_sesion, mundo, tarea_ajena_bloqueada):  # noqa: F811
    id_tarea, otra, _cursor = tarea_ajena_bloqueada
    iniciar_sesion(usuario_id=ID_ADMIN, rol_id=1)

    hilo, resultado = _en_hilo(lambda: client.put(f"/api/tareas/{id_tarea}/prioridad", json={"prioridad": "ALTA"}))
    hilo.join(1.0)
    assert hilo.is_alive()

    otra.rollback()
    hilo.join(15)

    assert resultado["respuesta"].status_code == 200
