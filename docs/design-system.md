# Design System Base - Nahan Asesores

## Principios visuales

El sistema conserva la identidad institucional existente: azul principal, turquesa secundario, superficies blancas y fondo gris suave. La interfaz debe sentirse como una herramienta SaaS empresarial: clara, predecible, sobria y facil de escanear.

## Paleta y tokens

Los tokens viven en `frontend/assets/css/variables.css`.

- Primario: `--color-primary` (`#123A6F`)
- Primario hover: `--color-primary-hover` (`#0F315F`)
- Primario suave: `--color-primary-soft`
- Secundario: `--color-secondary` (`#2FC3C7`)
- Fondo: `--color-background`
- Superficie: `--color-surface`
- Superficie secundaria: `--color-surface-secondary`
- Texto principal: `--color-text-primary`
- Texto secundario: `--color-text-secondary`
- Texto tenue: `--color-text-muted`
- Bordes: `--color-border`, `--color-border-strong`
- Estados: `--color-success`, `--color-warning`, `--color-danger`, `--color-info`
- Radios: `--radius-sm`, `--radius-md`, `--radius-lg`
- Sombras: `--shadow-sm`, `--shadow-md`, `--shadow-lg`
- Espaciado: `--spacing-1` a `--spacing-6`

## Tipografia

La familia actual se mantiene en `--font-family`. Las jerarquias base son:

- `h1` y `.page-title` para titulo de pagina.
- `h2` y `.section-title` para secciones.
- `h3` y `.card-title` para titulos de tarjeta.
- `.subtitle`, `.page-subtitle` y `.text-secondary` para texto complementario.
- `.text-muted` y `.help-text` para ayudas.

## Espaciados

Usar los tokens `--spacing-1` a `--spacing-6`. Evitar valores sueltos nuevos salvo necesidades puntuales de compatibilidad.

## Botones

Los botones base estan en `frontend/assets/css/buttons.css`.

- `.btn`
- `.btn-primary`
- `.btn-secondary`
- `.btn-danger`
- `.btn-warning`
- `.btn-success`
- `.btn-icon`
- `.btn-sm` o `.btn-small`
- `.is-loading`

Los botones deshabilitados deben usar `disabled` real cuando corresponda.

## Tarjetas

Las tarjetas base usan fondo blanco, borde discreto, radio medio y sombra suave. Clases principales:

- `.card`
- `.usuarios-card`
- `.metric-card`

Los CSS de modulo pueden seguir existiendo temporalmente, pero deben tender a reutilizar estos patrones.

## Tablas

Las tablas deben usar:

- `.table`
- `.dashboard-table`
- `.clientes-table`
- `.tareas-table`
- `.table-responsive` para scroll horizontal interno.

No se debe permitir que una tabla ancha rompa el layout general.

## Badges

Los badges usan `.badge` y variantes por estado real:

- `activo`, `inactivo`
- `estado-pendiente`
- `estado-en_proceso`
- `estado-en_revision`
- `estado-completada`
- `estado-cancelada`
- `prioridad-baja`
- `prioridad-media`
- `prioridad-alta`
- `prioridad-urgente`
- `area-juridica`
- `area-contable`
- `area-ambas`

No crear estados visuales que no existan funcionalmente.

## Formularios

Usar:

- `.form-group`
- `.form-label`
- `.form-input`
- `.form-grid`
- `.form-full`
- `.form-help`
- `.form-error`

Los campos deben conservar label visible y foco accesible.

## Sidebar

La barra lateral se genera desde `frontend/assets/js/navigation.js`.

- Expandida: muestra marca, textos, modulos, administracion si aplica y sesion.
- Colapsada: muestra marca compacta, abreviaturas como iconos y avatar.
- La preferencia visual se guarda en `localStorage` con `nahan_sidebar_collapsed`.
- Identidad, rol y permisos siempre vienen desde `/api/auth/me`.

## Topbar

La barra superior se genera desde `frontend/assets/js/topbar.js`.

- Muestra titulo de pantalla.
- Muestra subtitulo cuando existe.
- Muestra fecha actual en espanol.
- Muestra estado neutro de notificaciones.
- Muestra usuario y cierre de sesion.

No hay busqueda global porque no existe RF ni endpoint para eso.

## Accesibilidad

- Mantener foco visible.
- Usar `aria-label` y `title` en controles compactos.
- No depender solo del color para acciones criticas.
- Mantener labels visibles en formularios.
- Mantener textos legibles en tablas y botones.

## Reglas de uso

- No introducir una paleta nueva sin revisar los tokens.
- No usar `localStorage` para identidad, roles ni permisos.
- No crear enlaces de modulos que no existan.
- No simular metricas, notificaciones ni busquedas.
- Mantener los CSS de modulo mientras haya compatibilidad pendiente.

## Componentes pendientes

- Redisenio profundo del temporizador.
- Panel lateral de detalle de clientes.
- Panel lateral de detalle de tareas.
- Estados visuales avanzados para carga por modulo.
- Revision completa de CSS antiguo duplicado.
