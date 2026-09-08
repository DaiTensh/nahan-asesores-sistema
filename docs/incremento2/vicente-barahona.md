# Vicente Barahona — Notificaciones y productividad

**Incremento 2 · 4 RF · 26 HH · rama `feature/inc2-notificaciones`**

Usuario para probar: `vicente.barahona@nahan.local` — contraseña `Nahan.2026`

> Esta ficha es la que lee Claude cuando dices «hola, soy Vicente».
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
git checkout -b feature/inc2-notificaciones
```

---

## Tus requerimientos

### 1. RF52 — Notificando Nuevas Asignaciones

Al asignar una tarea, generar el aviso dirigido al nuevo responsable.

**Archivos:** `backend/routes/notificaciones_routes.py` (nuevo) · `backend/routes/tareas_routes.py`

**Criterios de aceptación**

- El aviso incluye el enlace a la tarea en `url_destino`.
- No se notifica al usuario que ejecuta la acción sobre sí mismo.

> **Primero define la función que genera una notificación y acuerda su firma con Matías (RF16) y Renato (RF26).** Los dos la van a llamar desde sus módulos.


### 2. RF51 — Notificando Internamente por Cambio de Estado

Al cambiar el estado de una tarea, avisar al responsable.

**Archivos:** `backend/routes/tareas_routes.py`

**Criterios de aceptación**

- Se dispara en `actualizar_estado_tarea`.
- El mensaje dice el estado anterior y el nuevo.


### 3. RF53 — Notificando el Vencimiento de Tareas

Proceso programado que evalúa las tareas próximas a vencer y genera los avisos.

**Archivos:** `deploy/systemd/nahan-vencimientos.service|.timer` (nuevos) · `backend/tareas_programadas.py` (nuevo)

**Criterios de aceptación**

- El proceso corre con un *systemd timer*.
- **Se puede ejecutar a mano**: sin eso no hay forma de demostrarlo en la presentación ni de capturar la evidencia de PT-53.1.
- No duplica avisos si se ejecuta dos veces el mismo día.

> `deploy/systemd/nahan.service` ya está en el repo y sirve de modelo.


### 4. RF39 — Visualizando la Productividad por Usuario

Indicadores de productividad individual: tareas completadas, tiempo promedio de resolución y carga vigente.

**Archivos:** `backend/routes/reportes_routes.py` · `frontend/reportes/productividad.html|js`

**Criterios de aceptación**

- Cantidad de tareas completadas por usuario y período.
- Tiempo promedio de resolución, medido **entre la asignación y el cierre**.
- Carga vigente: tareas en PENDIENTE o EN_PROCESO.
- Filtrable por área y por rango de fechas.
- Ordenado de mayor a menor cantidad de tareas completadas, para poder comparar usuarios del mismo rol.
- Solo rol ADMINISTRADOR.

> El criterio del promedio está fijado en la ficha del caso de uso CU-48 del informe. Si lo cambias, hay que actualizar esa ficha.


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
git push -u origin feature/inc2-notificaciones
```

y abres el Pull Request hacia `main`.

## Con quién te tienes que coordinar

- **Función que genera una notificación**: la defines tú. La consumen Matías Rodríguez, Renato Villalobos. Publícala el primer día.
- **Estructura de la vista frontend/reportes/**: la define quien llegue primero. Espera su definición antes de programar contra ella.
