# Renato Villalobos — Seguridad y exportación a PDF

**Incremento 2 · 3 RF · 26 HH · rama `feature/inc2-seguridad-export`**

Usuario para probar: `renato.villalobos@nahan.local` — contraseña `Nahan.2026`

> Esta ficha es la que lee Claude cuando dices «hola, soy Renato».
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
git checkout -b feature/inc2-seguridad-export
```

---

## Tus requerimientos

### 1. RF26 — Restableciendo Contraseñas

Flujo de restablecimiento por correo con token de un solo uso, más aviso interno al administrador.

**Archivos:** `backend/routes/auth_routes.py` · `backend/utils/correo.py` (nuevo) · tabla nueva `token_recuperacion`

**Criterios de aceptación**

- Tabla `token_recuperacion` con id_usuario, token único, fecha de emisión, fecha de expiración y marca de uso.
- El enlace llega al correo del usuario y el aviso al administrador queda en `notificacion`.
- Si el correo no corresponde a una cuenta activa, la respuesta es idéntica: no se revela si existe.
- El token se invalida al usarlo y al expirar.

> El EC2 bloquea el puerto 25: SMTP por 587 con autenticación, credenciales en variables de entorno, nunca en el código. **La cuenta de correo sigue sin definirse**: resuélvela el primer día o RF26 se atasca.


### 2. RF38 — Filtrando Reportes por Rango de Fechas

Filtro de rango de fechas sobre los reportes, con selector manual y atajos de período.

**Archivos:** `backend/routes/reportes_routes.py` · `frontend/reportes/reportes.js`

**Criterios de aceptación**

- Atajos «última semana», «último mes» y «año actual».
- Si la fecha de inicio es posterior a la de término, se rechaza el rango antes de consultar.
- El filtro se combina con los demás criterios.
- El período aplicado queda visible en el reporte y guardado en los `parametros` de `reporte`.

> Depende de los endpoints de Benjamín (RF31, RF32). Empieza por aquí dentro de tu bloque: es lo más liviano y lo necesitas para RF34.


### 3. RF34 — Exportando Reportes en Formato PDF

Exportar a PDF cualquier reporte generado, conservando su estructura.

**Archivos:** `backend/routes/reportes_routes.py` · `requirements.txt`

**Criterios de aceptación**

- Encabezado con nombre del reporte, período consultado y fecha de generación.
- El PDF mantiene la estructura del reporte en pantalla.
- Descarga directa desde el navegador, sin software adicional en el cliente.

> No compongas el PDF a partir del HTML de la pantalla: vuelve a consultar con los parámetros guardados en `reporte`, para que el archivo refleje datos vigentes. Comparte esa función de consulta con Elías (RF35).


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
git push -u origin feature/inc2-seguridad-export
```

y abres el Pull Request hacia `main`.

## Con quién te tienes que coordinar

- **Función que genera una notificación**: la define Vicente Barahona. Espera su definición antes de programar contra ella.
- **Formato de respuesta del módulo de reportes**: la define Benjamín Contreras. Espera su definición antes de programar contra ella.
- **Capa de consulta compartida para exportar**: la defines tú. La consumen el resto del equipo. Publícala el primer día.
- **Estructura de la vista frontend/reportes/**: la define quien llegue primero. Espera su definición antes de programar contra ella.
