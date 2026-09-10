"""RF53 — Notificando el Vencimiento de Tareas.

Proceso programado (ver `deploy/systemd/nahan-vencimientos.service|.timer`)
que avisa al responsable de cada tarea cuyo vencimiento cae dentro de los
próximos `DIAS_ANTICIPACION_VENCIMIENTO` días (3 por defecto — no hay un
valor fijado en Requerimientos.xlsx ni en el Backlog; se definió con el
equipo al programar este RF) y que todavía no está en un estado final.

Se puede ejecutar a mano, sin depender del timer, para la demostración o
para capturar la evidencia de PT-53.1:

    python -m backend.tareas_programadas

No duplica avisos si se ejecuta más de una vez el mismo día: antes de
insertar, comprueba si ya existe una notificación del mismo tipo y para la
misma tarea generada hoy.
"""
import logging
import os

from backend.config.db import get_connection
from backend.routes.notificaciones_routes import crear_notificacion
from backend.routes.tareas_routes import ESTADOS_FINALES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TIPO_NOTIFICACION = "VENCIMIENTO_PROXIMO"
DIAS_ANTICIPACION_POR_DEFECTO = 3


def _dias_anticipacion():
    try:
        dias = int(os.getenv("DIAS_ANTICIPACION_VENCIMIENTO", DIAS_ANTICIPACION_POR_DEFECTO))
    except (TypeError, ValueError):
        return DIAS_ANTICIPACION_POR_DEFECTO

    return dias if dias > 0 else DIAS_ANTICIPACION_POR_DEFECTO


def _ya_notificada_hoy(cursor, id_usuario, url_destino):
    cursor.execute(
        """
        SELECT 1 FROM notificacion
        WHERE id_usuario = %s AND tipo = %s AND url_destino = %s
          AND DATE(fecha) = CURDATE()
        """,
        (id_usuario, TIPO_NOTIFICACION, url_destino)
    )
    return cursor.fetchone() is not None


def notificar_vencimientos_proximos(dias=None):
    """Ejecuta una pasada del proceso.

    Devuelve la cantidad de avisos efectivamente creados (no cuenta los que
    se omitieron por ya existir).
    """
    dias = dias if dias is not None else _dias_anticipacion()
    connection = None
    cursor = None
    creadas = 0

    try:
        connection = get_connection()

        if connection is None:
            logger.error("No se pudo conectar a MySQL; se aborta esta pasada.")
            return 0

        cursor = connection.cursor(dictionary=True)

        marcadores_estados_finales = ", ".join(["%s"] * len(ESTADOS_FINALES))
        cursor.execute(
            f"""
            SELECT id_tarea, id_responsable, titulo, fecha_vencimiento
            FROM tarea
            WHERE fecha_vencimiento IS NOT NULL
              AND fecha_vencimiento BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL %s DAY)
              AND estado NOT IN ({marcadores_estados_finales})
            """,
            (dias, *ESTADOS_FINALES)
        )
        tareas = cursor.fetchall()

        for tarea in tareas:
            url_destino = f"/frontend/tareas/detalle_tarea.html?id={tarea['id_tarea']}"

            if _ya_notificada_hoy(cursor, tarea["id_responsable"], url_destino):
                continue

            crear_notificacion(
                cursor,
                tarea["id_responsable"],
                TIPO_NOTIFICACION,
                f"La tarea \"{tarea['titulo']}\" vence el {tarea['fecha_vencimiento']}",
                url_destino,
            )
            creadas += 1

        connection.commit()
        logger.info(
            "Vencimientos revisados: %s tarea(s) evaluadas, %s aviso(s) creado(s).",
            len(tareas), creadas
        )
        return creadas

    except Exception:
        if connection:
            connection.rollback()
        logger.exception("Error al notificar vencimientos próximos")
        raise

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def main():
    notificar_vencimientos_proximos()


if __name__ == "__main__":
    main()
