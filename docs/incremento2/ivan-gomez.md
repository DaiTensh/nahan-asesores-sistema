# Iván Gómez — Adjuntos de tarea y redistribución

**Incremento 2 · 3 RF · 20 HH · rama `feature/inc2-adjuntos-tarea`**

Usuario para probar: `ivan.gomez@nahan.local` — contraseña `Nahan.2026`

> Esta ficha es la que lee Claude cuando dices «hola, soy Iván».
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
git checkout -b feature/inc2-adjuntos-tarea
```

---

## Tus requerimientos

### 1. RF54 — Adjuntando Archivos a Tareas

Subir archivos asociados a una tarea, con límite de tamaño y de tipo.

**Archivos:** `backend/routes/documentos_routes.py` · tablas `documento` y `tarea_documento` (ya existen)

**Criterios de aceptación**

- Límite de tamaño y lista blanca de extensiones, ambos configurables.
- El nombre del archivo se sanitiza: nada de rutas relativas ni `..`.
- Queda registrado quién subió el archivo y cuándo.

> Los archivos van al **volumen del EC2**, no a S3. En local, a una carpeta fuera del repositorio o ignorada por git: no commitees archivos subidos.


### 2. RF55 — Descargando Archivos Asociados a Tareas

Descargar los adjuntos de una tarea desde la interfaz.

**Archivos:** `backend/routes/documentos_routes.py` · `deploy/nginx/`

**Criterios de aceptación**

- Se verifica que el archivo pertenezca a la tarea antes de entregarlo.
- Solo puede descargarlo quien tiene acceso a la tarea.
- La descarga queda registrada.


### 3. RF19 — Reasignando y Redistribuyendo Tareas

Redistribuir la carga de trabajo entre usuarios o entre áreas.

**Archivos:** `backend/routes/tareas_routes.py` · `frontend/tareas/tareas.js`

**Criterios de aceptación**

- Permite mover varias tareas de un responsable a otro en una sola operación.
- Cada movimiento queda en `auditoria`.
- Muestra la carga actual de origen y destino antes de confirmar.

> RF16 (Matías) es la reasignación de una tarea; lo tuyo es la operación masiva. Reutiliza su función, no escribas otra.


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
git push -u origin feature/inc2-adjuntos-tarea
```

y abres el Pull Request hacia `main`.

## Con quién te tienes que coordinar

- **Endpoints sobre la tabla DOCUMENTO**: la defines tú. La consumen el resto del equipo. Publícala el primer día.
