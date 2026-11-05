# -*- coding: utf-8 -*-
"""`database/seed_dev.py --reset` contra un MySQL real y desechable.

--reset debe poder borrar lo sembrado aunque la aplicación ya haya llenado las tablas hijas (revisión de
tareas, comentarios, documentos, observaciones, avisos de recuperación, tiempo y cobros). Antes fallaba con el
error 1451 (clave foránea) en cuanto alguien enviaba una tarea a revisión, y dejaba a la persona sin poder
recargar sus datos de prueba.
"""
import os

import pytest

from tests.mysql_desechable import herramientas_disponibles
from tests.test_rut_mysql_real import mundo, servidor  # noqa: F401  (fixtures compartidas)

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)

TABLAS_DE_USO = ("revision_tarea", "comentario_tarea", "tarea_documento", "documento", "observacion_cliente",
                 "cliente_reciente", "token_recuperacion", "tiempo_trabajado", "cobro")


def _contar(mundo, tabla):  # noqa: F811
    return mundo.consulta(f"SELECT COUNT(*) AS n FROM {tabla}")[0]["n"]


def _usar_la_aplicacion(mundo):  # noqa: F811
    """Inserta las filas que crea el uso normal sobre lo sembrado, más un cliente y una tarea ajenos."""
    tarea = mundo.consulta("SELECT id_tarea, id_cliente, id_area, id_responsable FROM tarea ORDER BY id_tarea LIMIT 1")[0]
    usuario = tarea["id_responsable"]
    tarifa = mundo.consulta("SELECT id_tarifa FROM tarifa_hora LIMIT 1")[0]["id_tarifa"]
    t, c = tarea["id_tarea"], tarea["id_cliente"]
    mundo.sql("INSERT INTO revision_tarea (id_tarea, id_revisor, accion) VALUES (%s, %s, 'ENVIO_REVISION')", (t, usuario))
    mundo.sql("INSERT INTO comentario_tarea (id_tarea, id_usuario, comentario) VALUES (%s, %s, 'comentario de prueba')", (t, usuario))
    mundo.sql("INSERT INTO documento (id_cliente, nombre_documento, url_archivo, subido_por) VALUES (%s, 'doc', 'x.pdf', %s)", (c, usuario))
    doc = mundo.consulta("SELECT MAX(id_documento) AS id FROM documento")[0]["id"]
    mundo.sql("INSERT INTO tarea_documento (id_tarea, id_documento) VALUES (%s, %s)", (t, doc))
    mundo.sql("INSERT INTO observacion_cliente (id_cliente, id_usuario, texto) VALUES (%s, %s, 'observación de prueba')", (c, usuario))
    mundo.sql("INSERT INTO cliente_reciente (id_usuario, id_cliente) VALUES (%s, %s)", (usuario, c))
    mundo.sql("INSERT INTO token_recuperacion (id_usuario, token_hash, fecha_expiracion) VALUES (%s, %s, NOW())", (usuario, "a" * 64))
    mundo.sql("INSERT INTO tiempo_trabajado (id_tarea, id_usuario, fecha, hora_inicio, hora_fin, horas_trabajadas) "
              "VALUES (%s, %s, CURDATE(), '09:00:00', '10:00:00', 1.00)", (t, usuario))
    mundo.sql("INSERT INTO cobro (id_cliente, id_tarea, id_tarifa, fecha, horas_cobradas, valor_hora, monto_total) "
              "VALUES (%s, %s, %s, CURDATE(), 1.00, 1000, 1000)", (c, t, tarifa))
    # Un cliente que no es de la siembra, con una tarea creada por una cuenta sembrada.
    mundo.sql("INSERT INTO cliente (rut, razon_social) VALUES ('12.000.008-K', 'Cliente ajeno a la siembra')")
    ajeno = mundo.consulta("SELECT id_cliente FROM cliente WHERE rut = '12.000.008-K'")[0]["id_cliente"]
    mundo.sql("INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo) VALUES (%s, %s, %s, %s, 'tarea de una cuenta sembrada')",
              (ajeno, tarea["id_area"], usuario, usuario))
    return ajeno


def test_reset_borra_lo_sembrado_aunque_la_aplicacion_ya_lo_haya_usado(mundo):  # noqa: F811
    primera = mundo.ejecutar("database/seed_dev.py")
    assert primera.returncode == 0, primera.stdout + primera.stderr
    ajeno = _usar_la_aplicacion(mundo)
    assert all(_contar(mundo, tabla) >= 1 for tabla in TABLAS_DE_USO)

    segunda = mundo.ejecutar("database/seed_dev.py", "--reset")

    assert segunda.returncode == 0, segunda.stdout + segunda.stderr
    assert [_contar(mundo, tabla) for tabla in TABLAS_DE_USO] == [0] * len(TABLAS_DE_USO)
    assert (_contar(mundo, "usuario"), _contar(mundo, "tarea")) == (7, 12), "se volvió a sembrar lo mismo"
    assert _contar(mundo, "cliente") == 7, "los 6 sembrados y el ajeno, que no se borra"
    assert mundo.consulta("SELECT razon_social FROM cliente WHERE id_cliente = %s", (ajeno,))[0]["razon_social"] == "Cliente ajeno a la siembra"
    assert mundo.consulta("SELECT COUNT(*) AS n FROM tarea WHERE id_cliente = %s", (ajeno,))[0]["n"] == 0, \
        "la tarea de una cuenta sembrada sobre un cliente ajeno se va con la cuenta"
