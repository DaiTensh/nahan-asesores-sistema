"""Notificaciones internas (RF51, RF52, RF53).

Expone `crear_notificacion`, la función acordada en la coordinación del
Incremento 2 (ver `docs/incremento2/equipo.json`): Matías Rodríguez (RF16) y
Renato Villalobos (RF26) la consumen desde sus propios módulos para no volver
a duplicar el INSERT a la tabla `notificacion`.

No se agregan endpoints HTTP porque ningún RF de este bloque los pide todavía
(no hay bandeja de notificaciones en el frontend); si esa pantalla se
construye más adelante, este archivo es el lugar natural para las rutas
`GET /notificaciones` y `PUT /notificaciones/<id>/leida`.
"""


def crear_notificacion(cursor, id_usuario, tipo, mensaje, url_destino=None, id_usuario_actor=None):
    """Inserta un aviso en `notificacion` para `id_usuario`.

    Si `id_usuario_actor` coincide con `id_usuario` no se inserta nada: el
    criterio de aceptación de RF52 pide no notificar a quien ejecuta la
    acción sobre sí mismo, y el mismo criterio es razonable para RF51 (no
    tiene sentido avisarle a alguien de un cambio que hizo él mismo).
    """
    if id_usuario_actor is not None and id_usuario_actor == id_usuario:
        return

    cursor.execute(
        """
        INSERT INTO notificacion (id_usuario, tipo, mensaje, url_destino)
        VALUES (%s, %s, %s, %s)
        """,
        (id_usuario, tipo, mensaje, url_destino)
    )
