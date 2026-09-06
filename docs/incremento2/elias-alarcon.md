# Elías Alarcón — Dashboard y exportación a Excel

**Incremento 2 · 5 RF · 26 HH · rama `feature/inc2-dashboard-export`**

Usuario para probar: `elias.alarcon@nahan.local` — contraseña `Nahan.2026`

> Esta ficha es la que lee Claude cuando dices «hola, soy Elías».
> Si algo aquí no calza con el código, avisa antes de programar: puede ser que
> el informe y el repositorio se hayan separado.

---

## Antes de empezar

```bash
python scripts/doctor.py      # ¿está listo el entorno?
python scripts/setup.py       # si falta algo
python scripts/dev.py         # levantar el sistema
```

El sistema queda en `http://127.0.0.1:5500/frontend/auth/login.html`.

Tu rama:

```bash
git checkout main && git pull origin main
git checkout -b feature/inc2-dashboard-export
```

---

## Tus requerimientos

### 1. RF42 — Visualizando Tareas Vencidas

Tareas no finalizadas cuya fecha de vencimiento ya pasó, destacadas en el panel.

**Archivos:** `backend/routes/tareas_routes.py` — `GET /api/tareas/vencidas` · `frontend/dashboard/dashboard.js`

**Criterios de aceptación**

- Muestra cliente, responsable y días de retraso.
- Excluye COMPLETADA y CANCELADA.
- Los datos de prueba ya traen tareas vencidas: se ve de inmediato.


### 2. RF43 — Visualizando Tareas Próximas a Vencer

Tareas cuya fecha de vencimiento cae dentro de un período configurable.

**Archivos:** `backend/routes/tareas_routes.py` — `GET /api/tareas/por-vencer`

**Criterios de aceptación**

- El número de días es configurable, no un valor fijo en el código.
- No repite las que ya están vencidas.


### 3. RF48 — Visualizando Tareas Prioritarias

Tareas de prioridad ALTA o URGENTE del usuario autenticado.

**Archivos:** `frontend/dashboard/dashboard.js` · `backend/routes/tareas_routes.py`

**Criterios de aceptación**

- Solo las del usuario en sesión, no las de otros.
- Ordenadas por prioridad y luego por fecha de vencimiento.


### 4. RF50 — Resumiendo por Estado de Tareas

Conteo de tareas agrupadas por estado en el panel principal.

**Archivos:** `backend/routes/tareas_routes.py` — `GET /api/tareas/resumen`

**Criterios de aceptación**

- Un conteo por cada uno de los cinco estados, incluidos los que estén en cero.
- El patrón de endpoint de indicadores ya existe: `resumen_clientes_dashboard` en `clientes_routes.py`.


### 5. RF35 — Exportando Reportes en Formato Excel

Exportar a `.xlsx` cualquier reporte generado.

**Archivos:** `backend/routes/reportes_routes.py` · `requirements.txt` (openpyxl)

**Criterios de aceptación**

- Una fila por tarea y los encabezados de columna del reporte.
- El archivo abre tanto en Excel como en LibreOffice Calc.
- Los filtros aplicados aparecen en el nombre del archivo.
- Descarga directa desde el navegador.

> Igual que el PDF: se vuelve a consultar con los parámetros guardados, no se exporta el HTML. Comparte la capa de consulta con Renato (RF34) para que el PDF y el Excel no puedan divergir.


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
git push -u origin feature/inc2-dashboard-export
```

y abres el Pull Request hacia `main`.

## Con quién te tienes que coordinar

- **Formato de respuesta del módulo de reportes**: la define Benjamín Contreras. Espera su definición antes de programar contra ella.
- **Capa de consulta compartida para exportar**: la defines tú. La consumen el resto del equipo. Publícala el primer día.
- **Estructura de la vista frontend/reportes/**: la define quien llegue primero. Espera su definición antes de programar contra ella.
