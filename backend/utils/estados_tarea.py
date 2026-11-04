"""Definición única de los estados de una tarea.

Una tarea está *activa* mientras exige trabajo o seguimiento: pendiente, en
proceso, pausada o en revisión. COMPLETADA y CANCELADA la cierran. Todo cálculo
de «tareas activas» (carga de trabajo, listados, vínculos de un cliente, control
de horas) debe usar esta definición: repetirla a mano hizo que, al agregarse
PAUSADA, algunos reportes la dejaran fuera.
"""

ESTADOS_TAREA_ACTIVA = ("PENDIENTE", "EN_PROCESO", "PAUSADA", "EN_REVISION")

# Fragmento para «WHERE estado IN …». Se arma solo con las constantes de arriba,
# nunca con datos del usuario.
SQL_ESTADOS_ACTIVOS = "(" + ", ".join(f"'{estado}'" for estado in ESTADOS_TAREA_ACTIVA) + ")"


def es_estado_activo(estado):
    return estado in ESTADOS_TAREA_ACTIVA
