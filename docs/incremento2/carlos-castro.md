# Carlos Castro — Documentos y observaciones de cliente

**Incremento 2 · 3 RF · 20 HH · rama `feature/inc2-documental-cliente`**

Usuario para probar: `carlos.castro@nahan.local` — contraseña `Nahan.2026`

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
git checkout -b feature/inc2-documental-cliente
```

---

## Tus requerimientos

### 1. RF07 — Registrando Referencias a Documentos de Clientes

Registrar referencias informativas a documentos del cliente, **sin** almacenar el archivo.

**Archivos:** `backend/routes/documentos_routes.py` (nuevo) · tabla `documento` (ya existe)

**Criterios de aceptación**

- Se guardan nombre, tipo, ubicación de referencia y observaciones.
- Queda registrado quién la ingresó y cuándo.
- No se puede repetir la misma referencia para el mismo cliente.

> Según el Documento 0, RF07 **no sube archivos**: solo la referencia. La subida real es RF54, de Iván. Pónganse de acuerdo antes de definir los endpoints: ambos escriben en `documento`.


### 2. RF08 — Visualizando Documentos Referenciados

Consultar la información referencial de los documentos de un cliente.

**Archivos:** `frontend/clientes/ficha_cliente.html|js`

**Criterios de aceptación**

- Muestra nombre, tipo, fecha de registro y observaciones.
- Ordenados por fecha de registro descendente.
- Sin documentos: mensaje «No se registran documentos asociados».


### 3. RF09 — Registrando Observaciones Internas de Clientes

Observaciones internas del cliente, visibles solo para usuarios autorizados.

**Archivos:** **tabla nueva `observacion_cliente`** · `backend/routes/clientes_routes.py` · `frontend/clientes/ficha_cliente.js`

**Criterios de aceptación**

- Tabla nueva con id_cliente, id_usuario, texto, fecha.
- La sección no se despliega para quien no tiene permiso: la verificación es en el backend, no solo escondiendo el div.
- El texto pasa por `escapeHtml()` al mostrarse.

> Es el único cambio de esquema de tu bloque. Escribe el `ALTER`/`CREATE` en `database/nahan_asesores.sql` y avisa al grupo para que reimporten.


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
git push -u origin feature/inc2-documental-cliente
```

y abres el Pull Request hacia `main`.

## Con quién te tienes que coordinar

- **Endpoints sobre la tabla DOCUMENTO**: la defines tú. La consumen el resto del equipo. Publícala el primer día.
