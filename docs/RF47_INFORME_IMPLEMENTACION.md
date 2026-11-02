# Informe de implementación RF47

## Resumen

RF47 registra por usuario las consultas exitosas de fichas de clientes activos y muestra en el dashboard hasta N clientes recientes, ordenados por última interacción. N es global, se configura por un administrador y tiene default 5 y rango 1–20. La auditoría existente no se reutiliza para lecturas.

## Rama y estado Git

- Rama: `feature/incremento4-rf47`.
- SHA base: `c92dc9a` (`main` actualizado desde `origin/main`).
- HEAD actual: `c92dc9a`; no se creó commit.
- Cambios locales sin stage; no se hizo commit, push ni PR.
- Migración no aplicada a ninguna base. No se conectó ni modificó una BD compartida.

## Implementación

- `backend/utils/clientes_recientes.py:1-24`: parámetro, default, rango y validación entera estricta.
- `backend/routes/clientes_routes.py:113-158`: UPSERT atómico al abrir una ficha existente y activa; `:167-198`: endpoint autenticado `/api/clientes/recientes`, filtrado por identidad de sesión, estado activo, orden por microsegundo y `LIMIT` parametrizado.
- `backend/routes/auth_routes.py:322-386`: GET/PUT administrativos para configurar el límite, con respuesta 400 para valores inválidos y auditoría del cambio.
- `database/migraciones/009_clientes_recientes.sql:1-21`: tabla con PK usuario-cliente, FKs con cascada, índice de usuario/fecha y parámetro global insertado con `INSERT IGNORE`. Comentarios al inicio describen el rollback manual. No hay backfill: aperturas previas no se pueden reconstruir.
- `database/nahan_asesores.sql` y `database/migrar.py`: instalación nueva y reconocimiento de la migración.
- `frontend/dashboard/dashboard.html:352-367` y `frontend/dashboard/dashboard.js:27,46,286-320`: sección independiente “Mis clientes recientes”, enlaces a fichas, estados de carga/vacío/error, escape HTML y recarga al restaurar desde bfcache. Se conserva “Últimos clientes registrados”.
- `frontend/usuarios/configuracion_sesion.html` y `frontend/usuarios/configuracion_sesion.js`: configuración N en la pantalla existente, protegida para administradores.
- `tests/test_rf47_clientes_recientes.py`: fixtures SQLite aislados y pruebas HTTP/backend.

## Criterios RF47

| Criterio | Implementación | Prueba | Resultado | Evidencia |
|---|---|---|---|---|
| T01 | GET de ficha activa instrumenta identidad autenticada | `test_rf47_t01_t05_registra_visitas_y_ordena_por_recencia` | PASÓ | Ficha HTTP 200 y registro del usuario |
| T02 | Default global 5 | `test_rf47_t02_limite_predeterminado_devuelve_hasta_cinco` | PASÓ | Devuelve cinco de seis visitas |
| T03 | Rango global 1–20 y límite aplicado | `test_rf47_t03_actualiza_limite_administrativo_valido` | PASÓ | N=1 devuelve 1; N=20 devuelve hasta los 6 existentes |
| T04 | Validación de enteros en backend | `test_rf47_t04_rechaza_limites_invalidos_sin_error_500` | PASÓ | 0, 21, decimal, booleano y null responden 400 |
| T05 | UPSERT actualiza recencia sin duplicar; orden descendente | `test_rf47_t01_t05_registra_visitas_y_ordena_por_recencia` | PASÓ | Una fila por usuario-cliente y reapertura al primer lugar |
| T06 | Filtro por usuario de sesión; `id_usuario` externo ignorado | `test_rf47_t06_historial_aislado_e_id_usuario_enviado_ignorado` | PASÓ | Usuario B no ve historial de A |
| T07 | Inactivos no se registran ni se listan | `test_rf47_t07_excluye_clientes_inactivos` | PASÓ | Ficha inactiva no añade fila y listado la excluye |
| T08 | Rol operativo requerido también para abrir ficha | `test_rf47_t08_usuario_sin_rol_operativo_no_consulta_recientes`; `test_rf47_consulta_de_ficha_no_autorizada_no_registra_interaccion` | PASÓ | 403; sin interacción escrita |
| T09 | FK `ON DELETE CASCADE` con eliminación física actual | `test_rf47_t09_eliminacion_definitiva_limpia_referencias` | PASÓ | La referencia desaparece al borrar cliente |
| T10 | Ficha inexistente no registra; prueba visual integral | `test_rf47_t10_ficha_inexistente_no_registra_interaccion` | PASÓ / NO VERIFICADA | 404 sin fila pasó; recorrido visual real no ejecutado |

## Pruebas y validación

- `py -V:3.14 -m pytest -vv tests/test_rf47_clientes_recientes.py`: **15 passed**.
- `py -V:3.14 -m pytest -q tests/test_rf47_clientes_recientes.py tests/test_rf56_cobertura_auditoria.py tests/test_rf59_inactividad.py`: **60 passed**, 2 warnings deprecados de `sqlite3` en el test RF56 (`tests/test_rf56_cobertura_auditoria.py:104`).
- RF13: las validaciones aisladas de fecha inicial y final pasaron **5 + 5**; además, la ejecución por subconjuntos mostró **8 pruebas adicionales aprobadas**. La suite completa de 26 tests no entregó resumen en la terminal, por lo que queda **NO VERIFICADA como suite completa**.
- Suite completa `py -V:3.14 -m pytest -q --maxfail=1`: la salida llegó al 12% (58 casos indicados como aprobados) sin resumen ni fallo visible; resultado **NO VERIFICADO**.
- `git diff --check`: sin errores.
- Diagnósticos del editor: sin errores en los archivos Python y JavaScript revisados.
- Parser local de migraciones: 009 se separa en 2 sentencias. No se ejecutó el script de migración.
- Prueba manual visual/E2E: **NO VERIFICADA**; no se levantó la aplicación contra MySQL ni se usó navegador.

El entorno disponible fue Python 3.14.4, mientras la documentación de dependencias del proyecto declara 3.9–3.13 para pruebas. Pytest y dependencias se instalaron solo en el Python de usuario; no se cambiaron archivos de dependencias del repositorio.

## Compatibilidad y riesgos pendientes

- La migración es aditiva y mantiene los registros existentes; el historial comienza vacío tras instalarla. Rollback manual: `DROP TABLE cliente_reciente` y eliminar el parámetro `CLIENTES_RECIENTES_LIMITE`. El rollback descarta las interacciones nuevas.
- Se usa autorización operativa idéntica a la ficha; el sistema actual no define permisos por cliente y RF47 no agrega ese modelo.
- La instrumentación registra lecturas exitosas de fichas activas; no registra listados, búsquedas, errores ni fichas inactivas. Las modificaciones no actualizan recientes porque el contrato aprobado define la consulta de ficha como interacción.
- Pendiente validar visualmente el flujo y ejecutar migración/pruebas de integración en una base local desechable compatible con MySQL 8. No ejecutar contra producción ni bases compartidas.
- La regresión completa no quedó demostrada por la salida parcial de la terminal; no hay fallos nuevos confirmados fuera de las pruebas RF47.
