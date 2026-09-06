# Registro de Revisiones

## Propósito

Este documento mantiene el historial de revisiones, auditorías y controles realizados sobre el proyecto.

---

# Estados

- 🔴 CRÍTICO
- 🟠 ALTO
- 🟡 MEDIO
- 🔵 BAJO
- 🟢 RESUELTO
- ⚪ PENDIENTE

---

# Reglas

Claude debe:

1. No eliminar revisiones anteriores.
2. Mantener historial cronológico.
3. Diferenciar problemas confirmados de posibles problemas.
4. No marcar problemas como resueltos sin evidencia.
5. Registrar archivos afectados.
6. Registrar requerimientos relacionados.
7. Registrar pruebas realizadas.
8. Registrar impacto en la rúbrica.
9. Registrar correcciones.
10. Registrar verificaciones posteriores.

---

# Plantilla

## REV-XXX — [Nombre]

**Fecha:** DD/MM/AAAA

**Tipo:** Revisión / Auditoría / Incremento / Entrega

**Responsable:** Claude / Equipo / Ambos

**Branch:** `nombre-branch`

**Commit:** `hash`

---

## 1. Objetivo

---

## 2. Alcance

---

## 3. Fuentes consultadas

- Documento 0.
- Incremento.
- Rúbrica.
- Dimensión Técnica.
- Google Drive.
- GitHub.
- Documentación del repositorio.

---

## 4. Estado general

- [ ] Correcto.
- [ ] Correcto con observaciones.
- [ ] Requiere correcciones.
- [ ] Bloqueado.

---

## 5. Requerimientos revisados

| ID | Estado | Evidencia | Observaciones |
|---|---|---|---|
| RF-XXX | 🟢/🟡/🔴 | Evidencia | Observación |

---

## 6. Problemas encontrados

### REV-XXX-P01 — [Título]

**Severidad:** 🔴 / 🟠 / 🟡 / 🔵

**Problema:**

**Ubicación:**

**Impacto:**

**Recomendación:**

**Estado:** ⚪ PENDIENTE

---

## 7. Arquitectura

**Estado:**

- [ ] Cumple.
- [ ] Cumple parcialmente.
- [ ] No cumple.
- [ ] No revisado.

**Observaciones:**

---

## 8. Base de datos

**Estado:**

- [ ] Cumple.
- [ ] Cumple parcialmente.
- [ ] No cumple.
- [ ] No revisado.

**Observaciones:**

---

## 9. Backend

**Estado:**

- [ ] Cumple.
- [ ] Cumple parcialmente.
- [ ] No cumple.
- [ ] No revisado.

**Observaciones:**

---

## 10. Frontend

**Estado:**

- [ ] Cumple.
- [ ] Cumple parcialmente.
- [ ] No cumple.
- [ ] No revisado.

**Observaciones:**

---

## 11. Seguridad

**Estado:**

- [ ] Sin problemas detectados.
- [ ] Requiere correcciones.
- [ ] No revisado.

**Observaciones:**

---

## 12. Pruebas

**Pruebas ejecutadas:**

| Prueba | Resultado | Observaciones |
|---|---|---|
| [Prueba] | PASS/FAIL | - |

---

## 13. Documentación

**Estado:**

- [ ] Actualizada.
- [ ] Parcialmente actualizada.
- [ ] Desactualizada.

**Documentos afectados:**

---

## 14. Rúbrica

**Estado:**

- [ ] Cumple.
- [ ] Cumple parcialmente.
- [ ] No cumple.
- [ ] No verificable.

**Observaciones:**

---

## 15. Acciones recomendadas

1. [ ] 🔴 Acción crítica.
2. [ ] 🟠 Acción importante.
3. [ ] 🟡 Acción recomendada.
4. [ ] 🔵 Mejora.

---

## 16. Correcciones

| Problema | Corrección | Branch | Commit | Estado |
|---|---|---|---|---|
| REV-XXX-P01 | Descripción | `branch` | `hash` | 🟢 |

---

## 17. Verificación posterior

**Fecha:**

**Branch:**

**Commit:**

**Resultado:**

- [ ] Problemas corregidos.
- [ ] Pruebas correctas.
- [ ] Documentación actualizada.
- [ ] Sin regresiones.
- [ ] Aprobado.
- [ ] Requiere nueva revisión.

---

# Revisiones

## REV-001 — Revisión general de documentación, código y seguridad

**Fecha:** 22/08/2026

**Tipo:** Revisión

**Responsable:** Claude

**Branch:** `feature/modificaciones-incremento1`

**Commit:** `691f283`

---

### 1. Objetivo

Revisión general del estado del proyecto (documentación, código y seguridad), solicitada por el equipo debido a que varios integrantes programan en paralelo y se necesita una visión consolidada del estado real.

---

### 2. Alcance

Estructura completa del repositorio: documentación (`docs/*.md`), backend (Flask), frontend, base de datos, configuración de despliegue, y estado del working tree (cambios sin commitear).

---

### 3. Fuentes consultadas

- GitHub (código del branch `feature/modificaciones-incremento1`).
- Documentación del repositorio (`CLAUDE.md`, `docs/*.md`).

No se consultó Google Drive (Documento 0, Incrementos, Rúbrica, Dimensión Técnica) en esta revisión — queda pendiente contrastar los hallazgos contra esas fuentes oficiales.

---

### 4. Estado general

- [x] Correcto con observaciones.

---

### 5. Requerimientos revisados

| ID | Estado | Evidencia | Observaciones |
|---|---|---|---|
| — | — | — | No se revisó trazabilidad de RF-XXX: no existe `requirements.md` en `docs/` (referenciado en `project_context.md` pero ausente). No verificable en esta revisión. |

---

### 6. Problemas encontrados

#### REV-001-P01 — XSS almacenado por inserción de datos de BD en `innerHTML` sin escapar

**Severidad:** 🟠 ALTO

**Problema:** En seis archivos del frontend se insertan campos provenientes de la base de datos (`razon_social`, `titulo` de tarea, etc.) directamente en `innerHTML` mediante template literals, sin sanitizar ni escapar.

**Ubicación (corregida tras revisar cada archivo completo, ver nota de verificación abajo):**
- `frontend/clientes/ficha_cliente.js`
- `frontend/clientes/filtrar_clientes.js`
- `frontend/dashboard/dashboard.js`

**Nota de verificación (22/08/2026):** al leer los seis archivos completos antes de corregir, se confirmó que `frontend/clientes/modificar_clientes.js`, `frontend/assets/js/usuarios_autocomplete.js` y `frontend/assets/js/clientes_autocomplete.js` **no** insertan datos de BD vía `innerHTML`; asignan los valores a `.value`/`.label`/`.textContent` de elementos del DOM (asignación de propiedad, no parseo de HTML), por lo que no son explotables por esta vía. Se corrige la ubicación original de P01 a los 3 archivos que sí usaban `innerHTML` con datos sin escapar.

**Impacto:** Esos campos se ingresan por formularios accesibles a usuarios con rol jurídico o contable (registrar cliente, crear tarea, etc.). Un usuario autenticado podría guardar HTML/JS malicioso en un campo de texto y ejecutarlo en el navegador de otro usuario —incluido un administrador— que visualice ese registro. Como la sesión se maneja por cookie (`credentials: "include"`), un script inyectado podría ejecutar acciones en nombre de la víctima. Adicionalmente, en `ficha_cliente.js` el campo `documento.url_archivo` se insertaba sin escapar dentro de un atributo `href`, lo que además de la inyección de HTML permitía un `javascript:` URI.

**Recomendación:** Reemplazar la inserción vía `innerHTML` de valores dinámicos por `textContent` (o una función de escape/sanitización) para todo dato que provenga de la base de datos.

**Corrección aplicada (22/08/2026):** se agregó una función local `escapeHtml()` en cada uno de los 3 archivos y se envolvió cada valor interpolado proveniente de la API en `escapeHtml(...)` antes de insertarlo en el `innerHTML`. Para el `href` de `documento.url_archivo` en `ficha_cliente.js` se agregó además `sanitizarUrl()`, que solo permite URLs `http(s)://` o rutas relativas (bloquea `javascript:` y otros esquemas), y se añadió `rel="noopener noreferrer"` al enlace. Los IDs numéricos usados en query strings de `href` (`id_cliente`) se pasaron por `encodeURIComponent`.

**Estado:** 🟢 RESUELTO — corregido en los 3 archivos confirmados vulnerables. No hay suite de pruebas automatizadas disponible para verificar por regresión (ver P04); se verificó manualmente por lectura de código y `node --check` (sintaxis) sobre los 3 archivos editados.

---

#### REV-001-P02 — Fuga de detalle de error interno en `/api/login`

**Severidad:** 🟡 MEDIO

**Problema:** El bloque `except` de la ruta de login devuelve `str(e)` directamente en la respuesta JSON, a diferencia del resto de las rutas del backend, que usan `logger.exception(...)` junto con un mensaje genérico.

**Ubicación:** `backend/routes/auth_routes.py`, líneas 77-80.

**Impacto:** Posible filtración de detalles internos (mensajes de error de MySQL, nombres de columnas, etc.) a un cliente no autenticado, ya que `/api/login` no requiere sesión previa.

**Recomendación:** Registrar el error con `logger.exception` y devolver un mensaje genérico, igual que en el resto de las rutas (`clientes_routes.py`, `usuarios_routes.py`, `tareas_routes.py`).

**Corrección aplicada (22/08/2026):** se agregó `import logging` y `logger = logging.getLogger(__name__)` (antes ausentes en este archivo) y se reemplazó `except Exception as e: return jsonify({"error": str(e)}), 500` por `except Exception: logger.exception("Error al iniciar sesión"); return jsonify({"error": "Error interno al iniciar sesión"}), 500`, igual que en el resto de las rutas.

**Estado:** 🟢 RESUELTO — verificado con `python3 -m py_compile`. No verificado con pruebas de integración (no hay suite de pruebas disponible, ver P04).

---

#### REV-001-P03 — Documentación de gobierno creada como plantilla, sin contenido real del proyecto

**Severidad:** 🔵 BAJO (vacío de trabajo pendiente, no un defecto)

**Problema:** Los archivos `docs/architecture.md`, `docs/decisions.md`, `docs/development.md`, `docs/project_context.md`, `docs/testing.md` y `docs/workflow.md` contienen únicamente la estructura/plantilla, sin describir aún la arquitectura real, decisiones tomadas ni convenciones específicas del código ya implementado. Además, `project_context.md` referencia `requirements.md` y `documentation.md`, que no existen en `docs/`.

**Ubicación:** `docs/architecture.md`, `docs/decisions.md`, `docs/development.md`, `docs/project_context.md`, `docs/testing.md`, `docs/workflow.md`.

**Impacto:** El equipo y Claude no cuentan todavía con una fuente confiable de contexto histórico del proyecto; riesgo de que futuras sesiones tomen decisiones sin conocer el estado real.

**Recomendación:** Completar progresivamente cada documento con el contenido real del proyecto ya programado, y crear o eliminar la referencia a `requirements.md` / `documentation.md` en `project_context.md`.

**Estado:** ⚪ PENDIENTE

---

#### REV-001-P04 — Cambios destructivos sin commitear en el working tree

**Severidad:** 🟠 ALTO (riesgo de pérdida de trabajo, no de seguridad)

**Problema:** El working tree tiene marcados como eliminados (sin commitear): `README.md`, `docs/deploy_aws_demo.md`, `docs/design-system.md`, `tests/conftest.py` y `tests/test_incremento1_regression.py` (1684 líneas de pruebas de regresión). `pytest.ini` sigue apuntando a `testpaths = tests`, por lo que actualmente no hay ninguna prueba que `pytest` pueda ejecutar.

**Ubicación:** raíz del repositorio y `tests/`.

**Impacto:** Si estos cambios se confirman sin reemplazo, se pierde la cobertura de pruebas de regresión del Incremento 1 y las instrucciones de instalación/despliegue.

**Recomendación:** Confirmar con el equipo si la eliminación es intencional (p. ej., reescritura en curso en otra sesión/rama). Si no lo es, restaurar con `git checkout -- <archivo>`. Claude no debe decidir esto unilateralmente (regla 18 de `CLAUDE.md`).

**Actualización (22/08/2026):** el equipo confirmó que la eliminación de la carpeta `tests/` fue intencional ("borramos la carpeta de pruebas automaticas, pero solo la carpeta, no tocamos nada de codigo"). **Sigue sin confirmarse** si la eliminación de `README.md`, `docs/deploy_aws_demo.md` y `docs/design-system.md` también fue intencional — no se debe asumir ninguna de las dos cosas.

**Actualización (23/08/2026):** el equipo confirmó que la eliminación de `README.md`, `docs/deploy_aws_demo.md` y `docs/design-system.md` también fue intencional, sin estar seguros de si era crítico. Evaluación de impacto real, ya con el conjunto nuevo de `docs/*.md` + `CLAUDE.md` en el repo (no comiteados, revisados en esta misma fecha):

- `docs/design-system.md` — riesgo bajo. Los tokens que documentaba (colores, radios, sombras, espaciado) siguen viviendo como fuente única de verdad en `frontend/assets/css/variables.css`; el archivo eliminado solo los describía en prosa. No hay pérdida funcional.
- `docs/deploy_aws_demo.md` — riesgo moderado. Contenía la única receta paso a paso para levantar la demo en EC2 (Security Groups, Nginx, Gunicorn, systemd, etc.). Los documentos nuevos (`docs/architecture.md`, `docs/project_context.md`, `CLAUDE.md`) solo mencionan que la arquitectura usa Nginx/Gunicorn/EC2 a nivel conceptual — no incluyen los comandos de instalación/configuración. Si la demo actual ya está desplegada y estable, esto no bloquea nada hoy; si en algún momento hay que redesplegarla desde cero o traspasarla a otra persona, ese conocimiento operativo ya no está en el repositorio.
- `README.md` — riesgo moderado-alto para efectos de entrega académica. Era el único lugar con la guía de "cómo correr el proyecto en local" (venv, `pip install -r requirements.txt`, creación de la BD). Ninguno de los documentos nuevos cubre esto: `docs/development.md` son convenciones de código, no instrucciones de arranque. No rompe nada en ejecución, pero un repositorio de entrega sin README con instrucciones de instalación es justamente el tipo de brecha que la rúbrica penaliza, y coincide con el problema que el propio usuario reportó (`python3 -m backend.app` dejó de funcionarle en local).

**Recomendación:** no restaurar los 3 archivos tal cual (contenido puede estar desactualizado frente al resto de `docs/*.md` nuevos); en su lugar, decidir si conviene redactar un `README.md` nuevo y breve (setup local) alineado con `docs/development.md`, y opcionalmente un `docs/deployment.md` que reemplace el contenido operativo de `deploy_aws_demo.md`. Pendiente de que el equipo decida si quiere que se redacten.

**Estado:** 🟢 RESUELTO (confirmación) — eliminación intencional confirmada para los 3 archivos. Impacto evaluado (ver arriba). Queda abierta, a criterio del equipo, la decisión de redactar reemplazos para `README.md` y `docs/deploy_aws_demo.md`.

---

#### REV-001-P05 — Dependencia declarada sin uso: `PyJWT`

**Severidad:** 🔵 BAJO

**Problema:** `PyJWT` está listado en `requirements.txt`, pero no se encontró ningún uso en `backend/`. La autenticación real del sistema es por sesión/cookie (Flask `session`), no por JWT.

**Ubicación:** `requirements.txt`.

**Impacto:** Ninguno funcional; posible confusión sobre el mecanismo de autenticación real.

**Recomendación:** Confirmar con el equipo si `PyJWT` es para un desarrollo futuro planeado o si puede retirarse de las dependencias.

**Estado:** ⚪ PENDIENTE

---

### 7. Arquitectura

**Estado:**

- [x] Cumple parcialmente.

**Observaciones:** La arquitectura implementada (Flask + Gunicorn + Nginx + MySQL, sesiones por cookie, blueprints por módulo) es coherente y consistente en todo el backend. No se comparó formalmente contra la Dimensión Técnica oficial (Google Drive) en esta revisión.

---

### 8. Base de datos

**Estado:**

- [x] No revisado.

**Observaciones:** Existe `database/nahan_asesores.sql`. No se validó en esta revisión contra 1FN/2FN/3FN ni contra el modelo físico oficial de Google Drive.

---

### 9. Backend

**Estado:**

- [x] Cumple parcialmente.

**Observaciones:** Buen uso consistente de SQL parametrizado (no se encontró ningún caso de concatenación insegura en las consultas revisadas), bcrypt para contraseñas, decoradores `login_required`/`roles_required` por rol, y registro de auditoría en cambios de clientes. Ver P02 y P05.

---

### 10. Frontend

**Estado:**

- [x] Requiere correcciones.

**Observaciones:** Ver P01 (XSS almacenado).

---

### 11. Seguridad

**Estado:**

- [x] Requiere correcciones.

**Observaciones:** Ver P01 y P02.

---

### 12. Pruebas

**Pruebas ejecutadas:**

| Prueba | Resultado | Observaciones |
|---|---|---|
| `pytest` | No ejecutable | `tests/` fue eliminado del working tree (ver P04); no hay pruebas disponibles para ejecutar en esta revisión. |

---

### 13. Documentación

**Estado:**

- [x] Parcialmente actualizada.

**Documentos afectados:** los 7 archivos de `docs/` (ver P03).

---

### 14. Rúbrica

**Estado:**

- [x] No verificable.

**Observaciones:** No se contrastó contra la rúbrica oficial de Google Drive en esta revisión.

---

### 15. Acciones recomendadas

1. [x] 🟠 Corregir XSS almacenado (P01). — Resuelto 22/08/2026.
2. [ ] 🟠 Resolver con el equipo el estado de los archivos eliminados sin commitear (P04). — `tests/` confirmado intencional; falta confirmar README.md y 2 archivos de `docs/`.
3. [x] 🟡 Corregir fuga de error interno en login (P02). — Resuelto 22/08/2026.
4. [ ] 🟡 Completar la documentación de gobierno con contenido real del proyecto (P03).
5. [ ] 🔵 Confirmar uso o remoción de `PyJWT` (P05).

---

### 16. Correcciones

| Problema | Corrección | Branch | Commit | Estado |
|---|---|---|---|---|
| REV-001-P01 | `escapeHtml()`/`sanitizarUrl()` en `ficha_cliente.js`, `filtrar_clientes.js`, `dashboard.js` (los otros 3 archivos listados originalmente no eran explotables, ver nota en P01) | `feature/modificaciones-incremento1` | Pendiente de commit | 🟢 |
| REV-001-P02 | `logger.exception` + mensaje genérico en `auth_routes.py` (login) | `feature/modificaciones-incremento1` | Pendiente de commit | 🟢 |
| REV-001-P04 | Ninguna corrección de código; se aclaró parcialmente con el equipo (ver P04) | — | — | ⚪ |
| REV-001-P03, P05 | Sin corrección aplicada en esta pasada (fuera de alcance de lo solicitado) | — | — | ⚪ |

**Adicional, no registrado originalmente en P01-P05:** se detectaron y corrigieron dos problemas de severidad 🟠 ALTO que esta revisión (REV-001) no había identificado, hallados en una revisión posterior de backend:

- **Sesión desactualizada / control de acceso obsoleto:** `backend/utils/auth.py`, función `obtener_usuario_actual()`, confiaba enteramente en datos guardados en la cookie de sesión al momento del login (`rol_id`, `nombre`, `area_id`). Si un administrador cambiaba el rol de un usuario o lo desactivaba, el usuario afectado conservaba sus permisos anteriores hasta que expirara o renovara su sesión. **Corrección:** se reescribió para consultar la BD en cada solicitud (solo se confía en `session["usuario_id"]` como clave), devolviendo `None` si el usuario no existe o su `estado != "ACTIVO"`, siguiendo el mismo patrón ya usado en `control_horas_routes.py` (`_obtener_usuario`/`_validar_usuario`).
- **`UnboundLocalError` potencial en el bloque `finally`:** siete funciones (`tareas_routes.py`: `listar_tareas_pendientes`, `asignar_tarea`, `actualizar_estado_tarea`, `actualizar_prioridad_tarea`; `usuarios_routes.py`: `listar_usuarios`, `obtener_usuario`, `desactivar_usuario`) no inicializaban `connection`/`cursor` en `None` antes del `try`. Si `get_connection()` fallaba antes de asignar `cursor`, el `finally` lanzaba `UnboundLocalError` en vez de responder con un error controlado. **Corrección:** se agregó `connection = None` / `cursor = None` al inicio de cada función, igual que en `crear_tarea` (que ya tenía el patrón correcto) y en `control_horas_routes.py`.

Ambos se verificaron con `python3 -m py_compile` sobre los 4 archivos backend editados (sin errores de sintaxis) y se revisó que no exista import circular entre `backend/utils/auth.py` y `backend/config/db.py`. No se pudo ejecutar una prueba funcional end-to-end (requiere conexión a MySQL y no hay suite de pruebas disponible, ver P04).

---

### 17. Verificación posterior

**Fecha:** 22/08/2026.

**Branch:** `feature/modificaciones-incremento1` (cambios en el working tree, sin commitear todavía).

**Commit:** Pendiente — el equipo debe revisar los cambios y crear el commit.

**Resultado:**

- [x] Problemas corregidos. — P01, P02 corregidos; P04 confirmado/cerrado (23/08/2026, ver arriba). P03, P05 siguen pendientes (ver sección 15).
- [ ] Pruebas correctas. — No verificable: `tests/` fue eliminado (P04) y no hay suite disponible para correr.
- [x] Documentación actualizada. — Este registro (`revision.md`).
- [ ] Sin regresiones. — No verificable sin suite de pruebas ni acceso a una BD MySQL de prueba desde este entorno.
- [ ] Aprobado. — Requiere que el equipo revise el diff antes de dar por cerrada esta revisión.
- [x] Requiere nueva revisión. — Recomendado antes de mergear: (1) que el equipo revise el diff de los 7 archivos corregidos, (2) que corra la suite de pruebas real (si se restaura) contra estos cambios, en especial el flujo de login/roles afectado por el fix de `obtener_usuario_actual()`.

---

## REV-002 — Investigación de parpadeo/recarga periódica en el frontend

**Fecha:** 23/08/2026.

**Motivo:** reporte del equipo — "la página web se recarga o presenta un parpadeo cada cierto tiempo, provocando una experiencia incómoda para el usuario."

### 1. Alcance de la investigación

Se revisó todo `frontend/` en busca de cualquier mecanismo de recarga/parpadeo periódico: `setInterval`/`setTimeout` (4 resultados en todo el proyecto), `fetch`/`XMLHttpRequest` (35 resultados en 19 archivos), `window.location.href`/`location.reload`/`<meta http-equiv="refresh">`, `visibilitychange`/`focus`/`storage`/`BroadcastChannel`/`EventSource`/`WebSocket` (0 resultados), e invocaciones de `cargarNavegacion()`/`cargarTopbar()` en las 14 páginas protegidas.

### 2. Resultado

**No se encontró ningún mecanismo de recarga o parpadeo periódico en el código del proyecto.** El único timer periódico real es `control_horas.js:425` (`setInterval(actualizarTemporizador, 1000)`), que solo actualiza el texto de un cronómetro (`textContent`) sin hacer `fetch` ni tocar el resto del DOM — descartado como causa. Todos los `fetch` se disparan una única vez en `DOMContentLoaded` o en respuesta a una acción del usuario. Todas las redirecciones (`window.location.href`) son guardas de sesión (usuario no autenticado → login) o navegación post-acción, no periódicas.

**Causa real identificada:** `frontend/assets/js/api_config.js` y `backend/app.py` (`DEFAULT_DEV_ORIGINS`) declaran explícitamente los orígenes `http://127.0.0.1:5500` / `http://localhost:5500` — el puerto por defecto de la extensión **Live Server de VS Code** (la propia variable se llama `liveServerOrigins`, confirmando que este es el flujo de desarrollo local ya adoptado por el equipo). Live Server inyecta en cada página que sirve un script que recarga la página completa cada vez que se guarda cualquier archivo del workspace (no solo el HTML abierto), lo cual explica la "recarga cada cierto tiempo". El "parpadeo" se debe a que, tras cada una de esas recargas, `cargarNavegacion()`/`cargarTopbar()` reconstruyen el sidebar/topbar desde un contenedor vacío después de esperar la respuesta de `/auth/me`.

**Confirmación con el equipo (23/08/2026):** el fenómeno no se observó en la demo de AWS, solo en desarrollo local — consistente con la causa identificada (Live Server no está presente en el despliegue de AWS).

### 3. Corrección aplicada

**Ninguna en el código del proyecto.** No existe nada que eliminar o modificar en `frontend/`/`backend/` para este problema: la causa es una herramienta de desarrollo externa (Live Server), no un defecto del sistema. Eliminar o alterar código sin una causa real en el código habría violado la regla de no corregir eliminando algo "sospechoso" sin antes confirmar que efectivamente es la causa.

**Recomendación operativa (fuera del código):** configurar `liveServer.settings.ignoreFiles` en VS Code para excluir `backend/**`, `docs/**` y archivos `.md`, de modo que solo cambios reales en `frontend/` disparen la recarga; o usar `python3 -m http.server 5500` en vez de Live Server durante sesiones de prueba manual prolongadas donde no se quiera ninguna recarga automática.

**Estado:** 🟢 CERRADO — causa identificada y confirmada por el equipo; no aplica corrección de código.

---

# Historial

| ID | Fecha | Tipo | Estado | Resumen |
|---|---|---|---|---|
| REV-001 | 22/08/2026 | Revisión | 🟡 | Revisión general de documentación, código y seguridad — XSS almacenado (P01) y fuga de error en login (P02) corregidos; además se corrigieron 2 problemas de backend hallados después (sesión desactualizada en `obtener_usuario_actual()`, `UnboundLocalError` en 7 funciones). P04 confirmado/cerrado el 23/08/2026. Pendientes: P03 (docs sin contenido real), P05 (dependencia `PyJWT` sin uso) |
| REV-002 | 23/08/2026 | Investigación | 🟢 | Investigación del parpadeo/recarga periódica reportado por el equipo. Causa: Live Server de VS Code (herramienta de desarrollo local), no el código del proyecto. Sin cambios de código. Confirmado por el equipo que no ocurre en la demo de AWS. |
