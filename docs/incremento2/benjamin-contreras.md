# Benjamín Contreras — Clientes y generación de reportes

**Incremento 2 · 4 RF · 28 HH · rama `feature/inc2-clientes-reportes`**

Usuario para probar: `benjamin.contreras@nahan.local` — contraseña `Nahan.2026`

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
git checkout -b feature/inc2-clientes-reportes
```

---

## Tus requerimientos

### 1. RF05 — Buscando Específicamente Clientes

Ampliar la búsqueda de clientes a más criterios de los que hoy soporta.

**Archivos:** `backend/routes/clientes_routes.py` (líneas 335-380) · `frontend/clientes/listar_clientes.js`

**Criterios de aceptación**

- Hoy `?buscar=` solo hace LIKE sobre `razon_social` y `rut`. Debe cubrir también correo, área responsable y estado.
- La búsqueda sigue siendo parametrizada: nada de concatenar el término en el SQL.
- Sin resultados, mensaje explícito.


### 2. RF61 — Panelando el Resumen del Cliente

Panel en la ficha del cliente con su estado, su área y la cantidad de tareas activas.

**Archivos:** `backend/routes/clientes_routes.py` — `/api/clientes/<id>/ficha` · `frontend/clientes/ficha_cliente.html|js`

**Criterios de aceptación**

- El panel muestra estado, área asociada y número de tareas en PENDIENTE o EN_PROCESO.
- Se resuelve en una sola llamada, no en tres.
- Todo lo que venga de la base pasa por `escapeHtml()` antes de entrar al DOM.


### 3. RF31 — Reportando Tareas por Cliente

Reporte de las tareas de un cliente dentro de un período, con estado, prioridad, responsable y fechas, más un resumen por estado.

**Archivos:** `backend/routes/reportes_routes.py` (nuevo) · `frontend/reportes/reportes.html|css|js` (nuevo)

**Criterios de aceptación**

- El reporte incluye todas las tareas del cliente en el período.
- Muestra un resumen con el conteo por estado.
- Deja visible el período consultado y la fecha de generación.
- Si no hay tareas: mensaje «No se registran tareas para los criterios seleccionados» y **no** se registra la generación.
- Cada generación efectiva se guarda en `reporte` con `tipo_reporte`, `parametros` (JSON) y `fecha_generacion`.

> Las tablas `reporte` y `area_reporte` ya existen en `database/nahan_asesores.sql`. No hay cambios de esquema.


### 4. RF32 — Reportando Tareas por Usuario Responsable

El mismo reporte, agrupado por usuario responsable en vez de por cliente.

**Archivos:** `backend/routes/reportes_routes.py`

**Criterios de aceptación**

- Solo rol ADMINISTRADOR accede al módulo de reportes.
- Ninguna tarea de otro responsable se filtra en el resultado.
- Comparte la misma función de consulta que RF31; no dupliques el SQL.

> **Publica el formato de la respuesta al grupo antes de programarlo.** Renato (RF34, RF38) y Elías (RF35) construyen encima; si el contrato cambia después, se les rompe.


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
git push -u origin feature/inc2-clientes-reportes
```

y abres el Pull Request hacia `main`.

## Con quién te tienes que coordinar

- **Formato de respuesta del módulo de reportes**: la defines tú. La consumen Renato Villalobos, Elías Alarcón. Publícala el primer día.
- **Estructura de la vista frontend/reportes/**: la define quien llegue primero. Espera su definición antes de programar contra ella.
