# Matías Rodríguez — Ciclo de vida de la tarea

**Incremento 2 · 6 RF · 30 HH · rama `feature/inc2-tareas-ciclo-vida`**

Usuario para probar: `matias.rodriguez@nahan.local` — contraseña `Nahan.2026`

> Esta ficha es la que lee Claude cuando dices «hola, soy Matías».
> Si algo aquí no calza con el código, avisa antes de programar: puede ser que
> el informe y el repositorio se hayan separado.

---

## Antes de empezar

```bash
bash scripts/doctor.sh      # ¿está listo el entorno?
bash scripts/setup.sh       # si falta algo
bash scripts/dev.sh         # levantar el sistema
bash scripts/test.sh        # ejecutar las pruebas
```

El script te imprime la dirección exacta al arrancar; normalmente
`http://127.0.0.1:5500/frontend/auth/login.html`. Si el 5500 está ocupado
(Live Server de VS Code) usa la dirección que te indique el script, no la de
Live Server: solo la del script sabe en qué puerto quedó la API.

Tu rama:

```bash
git checkout main && git pull origin main
git checkout -b feature/inc2-tareas-ciclo-vida
```

---

## Tus requerimientos

### 1. RF63 — Visualizando el Detalle Completo de Tarea

Pantalla con toda la información de una tarea en una sola vista: responsable, estado, prioridad, cliente, fechas, descripción, historial de cambios y archivos adjuntos.

**Archivos:** `backend/routes/tareas_routes.py` · `frontend/tareas/detalle_tarea.html|css|js`

**Criterios de aceptación**

- Endpoint `GET /api/tareas/<id>` que devuelva la tarea con su cliente, su responsable y su área resueltos, no solo los id.
- Un usuario sin rol ADMINISTRADOR solo puede abrir el detalle de tareas donde es responsable.
- La vista muestra los adjuntos cuando existen y un vacío explícito cuando no.

> Es la pantalla desde la que cuelgan RF64, RF65 y los adjuntos de Iván. Hazla primero.


### 2. RF64 — Editando Tareas Existentes

Editar título, descripción, responsable, prioridad y fecha límite mientras la tarea no esté COMPLETADA ni CANCELADA.

**Archivos:** `backend/routes/tareas_routes.py` · `frontend/tareas/editar_tarea.html|css|js`

**Criterios de aceptación**

- Cada cambio queda registrado en `auditoria` con el valor anterior y el nuevo.
- Una tarea COMPLETADA o CANCELADA no se puede editar: el sistema lo impide y lo explica.
- La fecha de vencimiento no puede quedar anterior a la fecha de creación.

> Usa la función de auditoría que ya escribe `clientes_routes.py` al cambiar el estado de un cliente; sigue ese patrón.


### 3. RF65 — Marcando Tarea como Completada

Acción explícita que pasa el estado a COMPLETADA, registra `fecha_finalizacion` y el usuario, y bloquea la tarea para edición.

**Archivos:** `backend/routes/tareas_routes.py` · `frontend/tareas/tareas.js`

**Criterios de aceptación**

- Solo rol ADMINISTRADOR, igual que hoy en `actualizar_estado_tarea`.
- Se guarda `fecha_finalizacion` con la hora del cierre.
- Después de cerrarla, la edición queda deshabilitada en la interfaz, no solo en el backend.

> Es el evento sobre el que Vicente calcula el tiempo promedio de resolución en RF39. Avísale cuando esté.


### 4. RF69 — Filtrando Tareas por Estado

Filtro del listado por PENDIENTE, EN_PROCESO, EN_REVISION, COMPLETADA y CANCELADA.

**Archivos:** `backend/routes/tareas_routes.py` · `frontend/tareas/tareas.js`

**Criterios de aceptación**

- El filtro se combina con los que ya existen, no los reemplaza.
- El estado seleccionado se mantiene al recargar el listado.
- Un estado sin resultados muestra un mensaje, no una tabla vacía sin explicación.


### 5. RF68 — Visualizando Tareas Asignadas a un Usuario Específico

Consulta de tareas por responsable.

**Archivos:** `backend/routes/tareas_routes.py` — `GET /api/tareas?id_responsable=`

**Criterios de aceptación**

- Un usuario sin rol ADMINISTRADOR solo puede consultar sus propias tareas.
- El selector de responsable usa el autocompletado que ya existe en `frontend/assets/js/usuarios_autocomplete.js`.


### 6. RF16 — Modificando la Asignación de Tareas

Reasignar una tarea a otro usuario dejando registro del responsable anterior y el nuevo.

**Archivos:** `backend/routes/tareas_routes.py`

**Criterios de aceptación**

- El cambio queda en `auditoria` con responsable anterior, nuevo y fecha.
- El nuevo responsable recibe una notificación.
- No se puede reasignar una tarea COMPLETADA o CANCELADA.

> Necesita la función de notificación de Vicente. Acuerda la firma con él el primer día antes de llamarla.


---

## Cuando termines cada RF

1. Que funcione de verdad contra MySQL, no en teoría.
2. Commit **tuyo**, en tu rama, empezando por el código del RF:
   `git commit -m "RF63 Detalle completo de tarea"`.
3. **Captura de pantalla** de la prueba funcional, guardada con el nombre del RF.
   Sin ella el RF no se puede documentar en el capítulo 10 del informe.
4. Fila actualizada en `Bitacora Sprint 2 - Grupo 22.xlsx`, hoja «Pila del Sprint»,
   con fecha real y HH reales.

Al cerrar el bloque completo:

```bash
git push -u origin feature/inc2-tareas-ciclo-vida
```

y abres el Pull Request hacia `main`.

## Con quién te tienes que coordinar

- **Función que genera una notificación**: la define Vicente Barahona. Espera su definición antes de programar contra ella.
