# Informe de implementación RF49

## A. Resumen ejecutivo

RF49 agrega al dashboard una lista de hasta 10 eventos reales de `auditoria`, ordenados del más reciente al más antiguo. La vista incluye acción, módulo, fecha, hora, responsable y enlace solo cuando el cliente o tarea aún existe. Los administradores pueden filtrar por módulo y acción. La lista se actualiza cada 30 segundos, pausa al salir de la página y reanuda al restaurar desde bfcache.

## B. Implementación previa

Se inspeccionaron las referencias locales y remotas. `origin/main` no contiene `/api/cambios-recientes`, `/api/cambios-recientes/filtros`, `frontend/dashboard/cambios_recientes.js` ni `tests/test_rf49_cambios_recientes.py`. El commit indicado `5a6c35e` y la rama `feature/incremento4-rf49` tampoco estaban disponibles en las referencias recibidas; no fue posible auditar ese contenido previo. Se reutilizó el mecanismo de auditoría existente sin modificar su escritura.

## C. Modificaciones

- Nuevo `GET /api/cambios-recientes`: acceso de administrador, límite fijo N=10, filtros opcionales validados, parámetros SQL y proyección sin datos anteriores/nuevos.
- Nuevo `GET /api/cambios-recientes/filtros`: devuelve módulos configurados y tipos de acción realmente registrados.
- El resultado enlaza clientes y tareas solo si existen en sus tablas. Eventos de otras tablas o referencias eliminadas se muestran sin enlace.
- Nueva sección de dashboard con estados de carga, error y vacío. Los filtros permanecen seleccionados al refrescar.
- Un único `setInterval` de 30 segundos; evita solicitudes concurrentes, se detiene en `pagehide` y se reanuda sin duplicarse en `pageshow` persistido.

## D. Archivos

- `backend/routes/historial_routes.py`
- `frontend/dashboard/dashboard.html`
- `frontend/dashboard/dashboard.css`
- `frontend/dashboard/cambios_recientes.js`
- `tests/test_rf49_cambios_recientes.py`
- `docs/RF49_INFORME_IMPLEMENTACION.md`

No se añadieron tablas, migraciones, dependencias ni cambios a RF47.

## E. Backend y auditoría

- El historial fuente es `auditoria`, consultado con `LEFT JOIN` a usuarios y a las tablas de cliente/tarea para resolver responsable y disponibilidad del registro.
- Orden: `fecha DESC, id_auditoria DESC`; límite: 10, fijo en backend.
- Módulo se resuelve desde `MODULO_POR_TABLA`; filtros se validan contra módulos existentes y `^[A-Z0-9_]{1,50}$`. Los valores se pasan como parámetros SQL.
- La respuesta no incluye `datos_anteriores` ni `datos_nuevos`, aunque estén guardados en auditoría.
- No se crean eventos al consultar el propio historial.

## F. Seguridad y enlaces

- Ambos endpoints requieren `ROL_ADMINISTRADOR`, igual que el historial global existente.
- Módulos y acciones inválidos devuelven 400; conexión/fallos internos se manejan con error controlado.
- Destinos confirmados en el código: ficha cliente `../clientes/ficha_cliente.html?id=…`; detalle tarea `../tareas/detalle_tarea.html?id=…`. No se generan enlaces para otras tablas, IDs inexistentes ni registros eliminados.
- El cliente crea enlaces mediante DOM y `textContent`, no inserta datos de auditoría como HTML.

## G. Pruebas

| Escenario | Resultado | Evidencia |
|---|---|---|
| Administrador consulta cambios reales | PASÓ | RF49: 8 pruebas |
| Usuario sin sesión/no administrador | PASÓ | Respuestas 401/403 en ambos endpoints |
| Orden, límite N=10 y campos requeridos | PASÓ | Eventos sintéticos de auditoría aislados |
| Filtro por módulo, tipo y combinación | PASÓ | Pruebas de integración Flask/SQLite |
| Filtros inválidos y respuesta vacía | PASÓ | 400 controlado y lista vacía |
| Enlaces a cliente/tarea existentes | PASÓ | Destinos y IDs resueltos por joins |
| Registro eliminado u otro módulo | PASÓ | No se devuelve destino de enlace |
| Privacidad de la respuesta | PASÓ | Campos `datos_anteriores`/`datos_nuevos` ausentes |
| Polling y conservación de filtros | PASÓ (estático) | Timer único, 30 s y parámetros verificados |
| Actualización en navegador/bfcache | NO VERIFICADA | No se ejecutó navegador ni prueba E2E |
| Auditoría compartida RF56 | PASÓ | No se cambió el registro de eventos |

## H. Resultados de pytest

- `py -V:3.14 -m pytest -vv tests/test_rf49_cambios_recientes.py`: **8 passed**.
- `py -V:3.14 -m pytest -q tests/test_rf49_cambios_recientes.py tests/test_rf56_historial_actividad.py tests/test_rf56_cobertura_auditoria.py`: **48 passed**, 2 warnings deprecados de SQLite originados en `tests/test_rf56_cobertura_auditoria.py:104`.
- `py -V:3.14 -m pytest -q tests/test_rf13_historial_cliente.py`: **26 passed**.
- `py -V:3.14 -m pytest -q --maxfail=1`: **371 passed, 1 failed**. El fallo fue `tests/test_rf46_alertas_notificaciones.py::test_solo_el_helper_central_inserta_en_notificacion`, que compara una ruta con `\` producida por Windows contra una ruta esperada con `/`. No afecta archivos RF49 y no se modificó ese test.
- Suite completa excluyendo ese test: el terminal no entregó resumen; resultado **NO VERIFICADO**.
- `git diff --check`: sin errores. Diagnósticos VS Code: sin errores en los archivos Python/JavaScript revisados.
- Node.js no está disponible, así que no se ejecutó `node --check`.
- No se conectó MySQL ni se inició la aplicación; no hubo prueba visual real.

El entorno de pruebas fue Python 3.14.4. Las dependencias se instalaron solo en el Python de usuario y no se modificaron los manifiestos del proyecto.

## I. Git y pendientes

- Rama local: `feature/incremento4-rf49`, creada desde `origin/main` después de comprobar que el árbol estaba limpio.
- SHA base/HEAD: `88682a38c8e3448a79c37cf68fa384c7ae021aca`, merge de RF47 a `main`, autor registrado `vicentebarahona`.
- El commit RF49 `5a6c35e` no existe en las referencias disponibles; su autoría no pudo verificarse.
- Cambios RF49 locales sin commit. No se hizo push, merge ni PR. La rama sigue sin publicar.
- Pendiente validar actualización automática y enlaces en navegador con una base local desechable y ejecutar la suite completa en un entorno con runner estable. No ejecutar migraciones ni pruebas contra bases compartidas o producción.
