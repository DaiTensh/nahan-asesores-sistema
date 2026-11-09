# Arquitectura del Sistema

## 1. Propósito

Este documento describe la arquitectura técnica del sistema desarrollado para Nahan Asesores.

Debe mantenerse alineado con la Dimensión Técnica oficial y con la implementación real del proyecto.

---

# 2. Arquitectura general

La aplicación utiliza una arquitectura web compuesta principalmente por:

```text
Usuario
   ↓
Nginx
   ↓
Gunicorn
   ↓
Flask
   ↓
Lógica de aplicación
   ↓
MySQL 8

## Tablas del esquema que la aplicación no usa

La revisión de la auditoría A0 (AUD-036) comprobó que tres tablas de `database/nahan_asesores.sql` no tienen
ninguna referencia en `backend/` ni en `frontend/` (el único código que las toca es el respaldo, que vuelca el
esquema completo):

| Tabla | Origen probable | Qué la reemplazó |
|---|---|---|
| `tiempo_trabajado` | Modelo inicial del registro de horas | `registro_tiempo` (RF71–RF73, con la tarifa congelada y el monto calculado; desde la migración 012 guarda también `origen` —temporizador o manual— y la `observacion` del registro manual) |
| `comentario_tarea` | Modelo inicial de la tarea | Las observaciones de la tarea y de la revisión (`revision_tarea`) |
| `area_reporte` | Modelo inicial de reportes | El reporte se arma por consulta; `reporte` guarda solo la generación |

Decisión: **no se eliminan antes de la entrega.** Están en los diagramas del Incremento 3, las pruebas de esquema y
el paquete de respaldo las incluye; quitarlas exigiría una migración, actualizar diagramas e informe y no aporta
nada a la demostración. En el Incremento 4 se documentan como «reservadas, sin uso». Si el equipo decide retirarlas
después, debe hacerse con una migración numerada (`database/migraciones/012_…sql`) y actualizar `nahan_asesores.sql`,
`database/migrar.py`, los diagramas y la prueba `tests/test_migraciones_mysql_real.py`.
