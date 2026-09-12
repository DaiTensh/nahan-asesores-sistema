# Registro de Revisiones

## Propósito

Este documento mantiene el historial de revisiones, auditorías y controles realizados sobre el proyecto.

Las menciones a herramientas y archivos retirados se conservan como antecedentes
históricos de esas revisiones; no constituyen instrucciones vigentes ni dependencias
del sistema.

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

Al registrar una revisión:

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

**Responsable:** Nombre del responsable o equipo

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

## REV-003 — Auditoría forense completa y reparación autónoma (backend, frontend, tests, entorno)

**Fecha:** 08/09/2026.

**Tipo:** Auditoría.

**Responsable:** Claude.

**Branch:** `auditoria-claude`.

**Commit:** Pendiente — cambios en el working tree, sin commitear todavía.

---

### 1. Objetivo

Auditoría forense agresiva de todo el proyecto (backend, frontend, base de datos, tests, entorno de desarrollo, seguridad OWASP, accesibilidad, performance) con reparación autónoma de los problemas encontrados dentro del alcance permitido por `CLAUDE.md`, a pedido explícito del usuario.

### 2. Alcance

Todo el repositorio: `backend/` (5 blueprints + utils + config), `frontend/` (17 páginas), `database/nahan_asesores.sql`, `tests/`, `scripts/` (doctor, dev, setup, seed), `docs/`. Se ejecutó la app real (API + MySQL local, ya sembrados) y se hicieron pruebas HTTP reales contra la API, además de `pytest`.

### 3. Fuentes consultadas

- Código del branch `auditoria-claude` (GitHub local).
- `docs/decisions.md`, `docs/revision.md`, `docs/incremento2/equipo.json`.
- `CLAUDE.md`, `README.md`.
- No se consultó Google Drive (Documento 0, Rúbrica, Dimensión Técnica) — no disponible en este entorno; los hallazgos de este REV no dependen de esas fuentes.

### 4. Estado general

- [x] Correcto con observaciones.

### 5. Requerimientos revisados

No aplica trazabilidad por RF — esta auditoría no implementó RF nuevos del Incremento 2, solo corrigió bugs/seguridad en funcionalidad ya existente (Incremento 1 + entorno). Ningún cambio toca alcance de los 28 RF comprometidos (regla 24 de `CLAUDE.md`).

### 6. Problemas encontrados y corregidos

#### REV-003-P01 — Suite de regresión rota: 13/61 tests fallando por desincronización con el seed de Incremento 2

**Severidad:** 🟠 ALTO (bloqueaba la confianza en la suite de pruebas, no una vulnerabilidad de producción).

**Problema:** `tests/test_incremento1_regression.py` fue escrito contra el seed antiguo de 3 usuarios (id 1=admin, 2=jurídica, 3=contable). `database/seed_dev.py` ahora siembra 7 usuarios con otro mapeo id→rol (commit `667ff7a`). Como `obtener_usuario_actual()` (corrección de seguridad de REV-001) resuelve el rol consultando la BD real en cada request, y la fixture `iniciar_sesion` nunca mockeaba esa conexión, 13 tests fallaban por comparar contra roles que ya no correspondían a esos IDs. Una corrida además contaminó la BD de desarrollo real (insertó `operativo@nahan.test`, id_usuario=8) porque un chequeo de rol que debía dar 403 pasó de largo.

**Ubicación:** `tests/conftest.py` (fixture `iniciar_sesion`), `tests/test_incremento1_regression.py` (`test_app_configura_cookies_y_cors_desde_entorno`, `test_auth_me_autenticado`).

**Corrección aplicada:** `iniciar_sesion` ahora también sustituye `backend.utils.auth.get_connection` por una fila controlada acorde a sus propios parámetros (`usuario_id`, `rol_id`, `area_id`, `estado`), desacoplando toda la suite del contenido real de la BD sembrada. `test_auth_me_autenticado` se reescribió con el mismo patrón (antes dependía de que el usuario 1 real se llamara "Usuario Prueba"). `test_app_configura_cookies_y_cors_desde_entorno` ahora hace `monkeypatch.delenv("DEBUG")` para no heredar el `DEBUG=true` del `.env` local vía `load_dotenv()`.

**Pruebas realizadas:** `python -m pytest tests/` — antes 48 passed/13 failed, después **61 passed** (VERIFICADO, ejecutado).

**Pendiente para el equipo:** la fila de contaminación `operativo@nahan.test` (id_usuario=8) sigue en la BD de desarrollo local de esta máquina — el bloqueo de comandos destructivos del entorno impidió que Claude la borrara. Se limpia con `python database/seed_dev.py --reset`.

**Estado:** 🟢 RESUELTO.

---

#### REV-003-P02 — `scripts/doctor.py` y `scripts/dev.py` daban falso positivo de "API corriendo" por el Receptor AirPlay de macOS

**Severidad:** 🟠 ALTO (bloqueaba por completo el arranque de la API en macOS con configuración de fábrica, sin ningún diagnóstico correcto).

**Problema:** ambos scripts asumían que "puerto 5000 ocupado" == "la API ya está corriendo" (`ocupado(5000)` como único criterio). En macOS, el Receptor AirPlay ocupa el puerto 5000 por defecto (Ajustes del Sistema → General → AirDrop y Handoff). Verificado en vivo: `curl http://127.0.0.1:5000/` en esta máquina responde `403` con cabecera `Server: AirTunes/960.13.1` — no es la API. `scripts/dev.py` por lo tanto se niega a levantar la API (exit 1) incluso en un checkout nuevo donde la API nunca corrió, y `scripts/doctor.py` reporta "ocupado — la API ya está corriendo" (falso).

**Ubicación:** `scripts/doctor.py` (`revisar_puertos`), `scripts/dev.py` (`main`).

**Corrección aplicada:** ambos scripts ahora, cuando el puerto 5000 está ocupado, hacen un `GET /` real y confirman que el cuerpo JSON sea `{"message": "API Nahan Asesores funcionando correctamente"}` antes de asumir que es la API propia. Si no lo es, `doctor.py` lo reporta explícitamente ("ocupado, pero no por esta API — en macOS suele ser el Receptor AirPlay") y `dev.py` imprime la causa probable y dos alternativas (desactivar el Receptor AirPlay, o fijar `FLASK_RUN_PORT` en `.env` **y** actualizar el puerto hardcodeado en `frontend/assets/js/api_config.js`).

**Pruebas realizadas:** VERIFICADO en vivo — `python scripts/doctor.py` y `python scripts/dev.py --api` ejecutados en esta máquina antes y después del fix; el mensaje pasó de "ocupado — la API ya está corriendo" (falso) a "ocupado, pero no por esta API — en macOS suele ser el Receptor AirPlay" (correcto, contrastado con `lsof`/`curl`).

**Hallazgo relacionado (no corregido, es config local del usuario):** en esta máquina la variable de entorno `FLASK_RUN_PORT` está exportada como `5001` en la sesión de shell del usuario (no en `.env`, que dice `5000`) — un workaround manual previo para este mismo problema. Como `frontend/assets/js/api_config.js` tiene el puerto de la API hardcodeado en `5000`, **el frontend servido en el navegador no puede hablar con esa API real en 5001**: toda petición desde la UI cae en el Receptor AirPlay. Esto es fuera del repositorio (variable de shell, no versionada) — no se modificó. Recomendación al equipo: desactivar el Receptor AirPlay y dejar de exportar `FLASK_RUN_PORT` manualmente, para que el flujo estándar (`scripts/dev.py`) funcione sin workarounds.

**Estado:** 🟢 RESUELTO (diagnóstico correcto) / ⚪ PENDIENTE (decisión del equipo sobre desactivar AirPlay vs. re-cablear el puerto).

---

#### REV-003-P03 — `PATCH /clientes/<id>/deshabilitar` no verificaba que el cliente existiera

**Severidad:** 🟡 MEDIO.

**Problema:** a diferencia de todos los demás endpoints de `clientes_routes.py`, `deshabilitar_cliente_rf3` no comprobaba `conexion is None` ni el resultado de la `UPDATE`. Deshabilitar un `id_cliente` inexistente devolvía `200 OK` "Cliente deshabilitado y registrado en auditoría" y además insertaba una fila de auditoría falsa (registraba un cambio de estado que nunca ocurrió). `eliminar_definitivo_cliente` tenía la misma falta del chequeo `conexion is None` (aunque sí validaba existencia).

**Ubicación:** `backend/routes/clientes_routes.py`, funciones `deshabilitar_cliente_rf3` y `eliminar_definitivo_cliente`.

**Corrección aplicada:** se agregó el chequeo `if conexion is None` a ambas funciones, y en `deshabilitar_cliente_rf3` se verifica `cursor.rowcount` tras la `UPDATE`: si es 0 se hace `rollback()` y se devuelve `404 Cliente inexistente`, antes de insertar el registro de auditoría.

**Pruebas realizadas:** VERIFICADO en vivo contra la API real — `PATCH /api/clientes/999999/deshabilitar` con sesión admin: antes `200` (falso positivo), después `404 {"error": "Cliente inexistente."}`. `python -m pytest tests/` sigue en 61/61 (el test existente que mockea una conexión falsa para `id_cliente=10` sigue pasando: la fila simulada siempre "existe" para ese mock).

**Estado:** 🟢 RESUELTO.

---

#### REV-003-P04 — Paginación de `/clientes/listado` sin validar tipo ni límite

**Severidad:** 🔵 BAJO.

**Problema:** `pagina`/`limite` se parseaban con `int(request.args.get(...))` sin manejo de error (un valor no numérico causaba `500` genérico en vez de `400`), y `limite` no tenía cota superior (un cliente podía pedir un `LIMIT` arbitrariamente grande).

**Ubicación:** `backend/routes/clientes_routes.py`, función `listado_general_paginado_clientes`.

**Corrección aplicada:** `try/except` alrededor del `int()` → `400` con mensaje claro; `pagina < 1` → `400`; `limite` acotado a `[1, 100]`.

**Pruebas realizadas:** VERIFICADO en vivo — `?pagina=abc` → `400` (antes `500`); `?pagina=-1` → `400`; `?limite=999999999` → responde normalmente con el límite acotado a 100, sin error.

**Estado:** 🟢 RESUELTO.

---

#### REV-003-P05 — `GET /tareas/pendientes` devolvía las tareas de todas las áreas a cualquier autenticado; el filtrado "solo mis tareas" era solo del frontend

**Severidad:** 🟠 ALTO (seguridad basada solo en ocultar datos en el cliente — expresamente señalado como inaceptable en la regla 12 de `CLAUDE.md`).

**Problema:** `frontend/tareas/tareas.js` ya filtraba el listado a `tarea.id_responsable === usuario.id_usuario` para no administradores, evidencia clara de la regla de negocio esperada. Pero el backend (`listar_tareas_pendientes`, solo `@login_required`) devolvía las tareas de **todas** las áreas y responsables a cualquier autenticado — un usuario jurídico podía ver, vía llamada directa a la API, títulos, descripciones y clientes de tareas del área contable (y viceversa), pese a que el sistema es para una empresa que maneja información jurídica y contable de clientes reales.

**Ubicación:** `backend/routes/tareas_routes.py`, función `listar_tareas_pendientes`.

**Corrección aplicada:** el backend ahora aplica la misma condición que ya aplicaba el frontend: si el usuario no es `ADMINISTRADOR`, se agrega `WHERE t.id_responsable = %s` con el id de sesión.

**Decisión consciente de NO extender esta corrección a `PUT /tareas/<id>/{asignar,estado,prioridad}`:** inicialmente apliqué la misma restricción de "solo el responsable" a estos tres endpoints de escritura, pero al correr `pytest` encontré que **la suite existente valida explícitamente lo contrario**: `test_usuario_juridico_puede_usar_estado_operativo` y `test_usuario_contable_puede_usar_estado_operativo` prueban que cualquier usuario operativo puede cambiar el estado de una tarea sin relación de pertenencia con ella (solo los estados finales COMPLETADA/CANCELADA están restringidos a administrador, lo cual sí se mantiene). Ante esta contradicción entre dos fuentes (el filtro del frontend vs. el comportamiento ya validado por tests), y siguiendo la regla 4 de `CLAUDE.md` ("Claude no debe elegir arbitrariamente" ante contradicciones), revertí la restricción en esos tres endpoints y la dejo señalada aquí para que el equipo decida el modelo real: ¿cualquier operativo puede colaborar en cualquier tarea (modelo actual, validado por tests) o solo en las propias (lo que sugiere el frontend)?

**Pruebas realizadas:** VERIFICADO en vivo — login como `elias.alarcon@nahan.local` (jurídica) → `GET /api/tareas/pendientes` devuelve 2 tareas, ambas con `id_responsable` igual al suyo (antes devolvía las de toda la empresa). `python -m pytest tests/` 61/61 sin regresiones.

**Estado:** 🟢 RESUELTO (lectura) / ⚪ PENDIENTE DE DECISIÓN DEL EQUIPO (escritura — ver arriba).

---

#### REV-003-P06 — `obtener_usuario_actual()` consultaba la BD dos veces por solicitud

**Severidad:** 🔵 BAJO (performance, no funcional).

**Problema:** varias rutas llaman `obtener_usuario_actual()` una vez a través de los decoradores `login_required`/`roles_required` y otra vez dentro del propio handler (p. ej. para obtener `id_creador`/`id_usuario`), duplicando una consulta idéntica a MySQL en cada solicitud.

**Ubicación:** `backend/utils/auth.py`, función `obtener_usuario_actual`.

**Corrección aplicada:** el resultado se memoriza en `flask.g` durante la solicitud (se limpia solo al terminar el request, comportamiento estándar de Flask). Transparente para todos los llamadores — misma firma, mismo contrato.

**Pruebas realizadas:** `python -m pytest tests/` 61/61. VERIFICADO funcionalmente en vivo (login, `/auth/me`, flujos de tareas/clientes con sesión activa responden igual que antes).

**Estado:** 🟢 RESUELTO.

---

#### REV-003-P07 — `GET /usuarios` sin restricción de rol expone directorio completo de personal a cualquier autenticado

**Severidad:** 🟡 MEDIO — **NO corregido, requiere decisión del equipo.**

**Problema:** a diferencia de todas las demás rutas de `usuarios_routes.py` (todas `@roles_required(ROL_ADMINISTRADOR)`), `GET /usuarios` (listado completo) solo exige `@login_required`. Cualquier usuario autenticado —jurídico o contable— puede pedir ese endpoint y recibe nombre, correo, rol, área y estado de **todo el personal**, incluidos los administradores.

**Por qué no lo corregí:** `frontend/assets/js/usuarios_autocomplete.js` depende de exactamente esos campos (`email`, `nombre_rol`, `nombre_area`) de **todos** los usuarios activos para el autocompletado de "responsable" al crear una tarea — funcionalidad usada por los tres roles (`frontend/tareas/tareas.js`). Restringir el endpoint a solo administrador rompería esa función real. Por el patrón consistente del resto del archivo (lectura amplia, escritura restringida a admin) parece un directorio interno de personal deliberado, no un descuido — pero no hay una decisión registrada en `docs/decisions.md` que lo confirme, así que no lo puedo asumir (regla 9 de `CLAUDE.md`, "no inventar reglas de negocio").

**Opciones para el equipo:**
1. Dejarlo como está (directorio interno de personal, visible a todo el staff autenticado) y documentarlo como decisión en `docs/decisions.md`.
2. Crear un endpoint mínimo separado (solo `id_usuario`, `nombres`, `estado`) para el autocompletado, y restringir `GET /usuarios` (con datos completos) a administrador.

**Estado:** ⚪ PENDIENTE DE DECISIÓN DEL EQUIPO.

---

#### REV-003-P08 — Accesibilidad: `<label>` sin `for` en 5 páginas; doble envío sin bloqueo de botón en `login`/`registrar_clientes`

**Severidad:** 🔵 BAJO.

**Problema:** 21 `<label>` en `login.html`, `usuarios/usuarios.html`, `usuarios/modificar_usuario.html`, `usuarios/desactivar_usuario.html`, `usuarios/asignar_rol.html` y `tareas.html` no tenían `for` apuntando al `id` del campo (clic en la etiqueta no enfocaba el input; lectores de pantalla no asociaban la etiqueta). Además, los botones de envío de `login.js` y `registrar_clientes.js` no se deshabilitaban durante el `fetch`, permitiendo doble clic/doble envío (mayor riesgo en `registrar_clientes.js`: podía intentar crear el mismo cliente dos veces).

**Ubicación:** ver archivos arriba.

**Corrección aplicada:** se agregó `for="<id>"` a los 21 labels. Se agregó `disabled` + texto de carga al botón durante el `fetch` en `login.js` y `registrar_clientes.js`, con `try/finally` para restaurarlo ante error.

**Pruebas realizadas:** ANALIZADO ESTÁTICAMENTE (no hay navegador en este entorno) + `node --check` sobre los 2 `.js` editados (sin errores de sintaxis). No verificado visualmente en navegador.

**Pendiente, no corregido por volumen/riesgo de regresión visual sin poder verificar en navegador:** el mismo problema de doble-envío existe en `cambiar_estado.js`, `eliminar_cliente.js`, `modificar_clientes.js`, `tareas.js`, `desactivar_usuario.js` (detalle completo en la sección 6 de este documento, hallazgos de los subagentes). Se prioriza no tocar más archivos de UI sin poder confirmar visualmente el resultado.

**Estado:** 🟢 RESUELTO (labels, doble-envío en login/registrar_clientes) / ⚪ PENDIENTE (doble-envío en los otros 5 archivos, ver arriba).

---

### 7. Arquitectura

**Estado:** [x] Cumple parcialmente.

**Observaciones:** patrón backend consistente y sólido (SQL parametrizado en todas las rutas revisadas, roles/áreas bien modelados, bloqueo de filas `FOR UPDATE` correcto en `control_horas_routes.py` para evitar carreras). El punto débil real es el entorno de desarrollo (P02) y la falta de una decisión registrada sobre el modelo de visibilidad entre áreas (P05, P07).

### 8. Base de datos

**Estado:** [x] Cumple.

**Observaciones:** esquema con FKs e índices coherentes (revisado `database/nahan_asesores.sql` completo). No se detectaron problemas de integridad referencial ni de normalización en esta pasada.

### 9. Backend

**Estado:** [x] Cumple parcialmente. Ver P03, P04, P05, P06, P07.

### 10. Frontend

**Estado:** [x] Cumple parcialmente. Ver P05 (backend, pero con causa visible en frontend), P08. Ver también el detalle completo de hallazgos NO corregidos (doble-envío en 5 archivos, `<h1>` duplicado en topbar, CSS muerto `sidebar.css`/`layout.css`, RUT sin validación de formato en frontend, `restringirFuncionalidad` no definida) reportado por los dos subagentes de auditoría de frontend — no se listan todos individualmente en este registro para no duplicar el informe final entregado al usuario en la conversación.

### 11. Seguridad

**Estado:** [x] Requiere correcciones (parcialmente aplicadas). Ver P05 (resuelto en lectura), P07 (pendiente de decisión).

**Observaciones adicionales:** se probó en vivo resistencia a inyección SQL en el login (`' OR '1'='1` en el campo email → `401` limpio, sin error) y acceso sin rol a endpoint admin-only (`403` correcto). No se encontraron secretos hardcodeados en el frontend ni en el backend.

### 12. Pruebas

**Pruebas ejecutadas:**

| Prueba | Resultado | Observaciones |
|---|---|---|
| `pytest tests/` | 61 passed (antes: 48 passed, 13 failed) | VERIFICADO, ver P01 |
| `python -m py_compile` sobre todo `backend/`, `scripts/dev.py`, `scripts/doctor.py`, `tests/*.py` | Sin errores | VERIFICADO |
| `node --check` sobre `login.js`, `registrar_clientes.js` | Sin errores | VERIFICADO |
| API real (login, `/auth/me`, roles, SQL injection, endpoints corregidos) vía `curl` contra `backend.app` corriendo en `127.0.0.1:5001` | Todo lo probado se comportó como se esperaba | VERIFICADO — ver detalle en cada hallazgo |
| Pruebas de UI real en navegador (botones, formularios, responsive) | No ejecutable | NO VERIFICABLE — no hay herramienta de navegador en este entorno |

### 13. Documentación

**Estado:** [x] Actualizada (este registro). `docs/decisions.md` sigue sin contenido real (ver REV-001-P03, aún pendiente).

### 14. Rúbrica

**Estado:** [x] No verificable — no se contrastó contra la rúbrica oficial de Google Drive en esta auditoría.

### 15. Acciones recomendadas

1. [x] 🟠 Reparar la suite de tests rota (P01). — Resuelto 08/09/2026.
2. [x] 🟠 Corregir el falso positivo de puerto 5000/AirPlay en `doctor.py`/`dev.py` (P02). — Resuelto (diagnóstico); pendiente decisión del equipo sobre AirPlay vs. re-cablear puerto.
3. [x] 🟡 Corregir `deshabilitar_cliente_rf3` sin chequeo de existencia (P03). — Resuelto.
4. [x] 🔵 Validar paginación de `/clientes/listado` (P04). — Resuelto.
5. [x] 🟠 Aplicar server-side el filtro "solo mis tareas" en `GET /tareas/pendientes` (P05). — Resuelto en lectura; pendiente decisión del equipo sobre escritura.
6. [x] 🔵 Cachear `obtener_usuario_actual()` por request (P06). — Resuelto.
7. [ ] 🟡 Decidir el modelo de visibilidad de `GET /usuarios` (P07). — Pendiente, requiere decisión del equipo.
8. [x] 🔵 Accesibilidad: labels sin `for`, doble-envío en login/registro de cliente (P08). — Resuelto parcialmente; queda doble-envío en 5 archivos más.

### 16. Correcciones

| Problema | Corrección | Branch | Commit | Estado |
|---|---|---|---|---|
| REV-003-P01 | `iniciar_sesion` mockea `auth.get_connection`; 2 tests reescritos | `auditoria-claude` | Pendiente de commit | 🟢 |
| REV-003-P02 | Verificación HTTP real antes de asumir "API corriendo" en `doctor.py`/`dev.py` | `auditoria-claude` | Pendiente de commit | 🟢 |
| REV-003-P03 | Chequeos `conexion is None` + `rowcount` en `deshabilitar_cliente_rf3`/`eliminar_definitivo_cliente` | `auditoria-claude` | Pendiente de commit | 🟢 |
| REV-003-P04 | Validación de `pagina`/`limite` en listado paginado | `auditoria-claude` | Pendiente de commit | 🟢 |
| REV-003-P05 | Filtro server-side en `GET /tareas/pendientes` | `auditoria-claude` | Pendiente de commit | 🟢 |
| REV-003-P06 | Cacheo de `obtener_usuario_actual()` en `flask.g` | `auditoria-claude` | Pendiente de commit | 🟢 |
| REV-003-P07 | Sin corrección — pendiente de decisión del equipo | — | — | ⚪ |
| REV-003-P08 | `for=` en 21 labels; disabled-durante-fetch en 2 formularios | `auditoria-claude` | Pendiente de commit | 🟢 |

### 17. Verificación posterior

**Fecha:** 08/09/2026.

**Branch:** `auditoria-claude` (cambios en el working tree, sin commitear).

**Commit:** Pendiente — el equipo debe revisar el diff y decidir si commitea.

**Resultado:**

- [x] Problemas corregidos. — P01 a P06, P08 corregidos (P08 parcialmente); P07 pendiente de decisión.
- [x] Pruebas correctas. — 61/61 en `pytest`, verificación en vivo contra API real.
- [x] Documentación actualizada. — Este registro.
- [x] Sin regresiones evidentes. — Suite completa sigue en verde después de cada cambio; no se detectaron efectos secundarios en las pruebas en vivo.
- [ ] Aprobado. — Requiere que el equipo revise el diff (15 archivos) y decida P02 (AirPlay/puerto) y P07 (visibilidad de `GET /usuarios`) antes de mergear.
- [x] Requiere nueva revisión. — Recomendado antes de mergear: que el equipo pruebe la UI real en navegador (bloqueado aquí por falta de esa herramienta) y decida P07.

---

# Historial

| ID | Fecha | Tipo | Estado | Resumen |
|---|---|---|---|---|
| REV-001 | 22/08/2026 | Revisión | 🟡 | Revisión general de documentación, código y seguridad — XSS almacenado (P01) y fuga de error en login (P02) corregidos; además se corrigieron 2 problemas de backend hallados después (sesión desactualizada en `obtener_usuario_actual()`, `UnboundLocalError` en 7 funciones). P04 confirmado/cerrado el 23/08/2026. Pendientes: P03 (docs sin contenido real), P05 (dependencia `PyJWT` sin uso) |
| REV-002 | 23/08/2026 | Investigación | 🟢 | Investigación del parpadeo/recarga periódica reportado por el equipo. Causa: Live Server de VS Code (herramienta de desarrollo local), no el código del proyecto. Sin cambios de código. Confirmado por el equipo que no ocurre en la demo de AWS. |
| REV-003 | 08/09/2026 | Auditoría | 🟡 | Auditoría forense completa con reparación autónoma: suite de tests rota reparada (13→0 fallos), falso positivo de puerto 5000/AirPlay corregido en `doctor.py`/`dev.py`, bugs de validación/existencia en `clientes_routes.py` y `tareas_routes.py` corregidos, N+1 de `obtener_usuario_actual()` cacheado, accesibilidad (labels, doble-envío) corregida en 2 formularios. Pendiente decisión del equipo: visibilidad de `GET /usuarios` (P07) y modelo de permisos de escritura sobre tareas ajenas (P05). No verificable: UI real en navegador (sin esa herramienta en este entorno). |
