# Estrategia de Pruebas

## 1. Propósito

Este documento define cómo se verificará el correcto funcionamiento del sistema.

El equipo debe utilizarlo para planificar y ejecutar pruebas cuando corresponda.

---

# 2. Objetivos

Las pruebas deben verificar:

- Requerimientos.

- Lógica de negocio.

- Integración.

- Base de datos.

- Frontend.

- Seguridad.

- Regresiones.

---

# 3. Tipos de pruebas

## Pruebas unitarias

Verifican funciones o componentes individuales.

---

## Pruebas de integración

Verifican la interacción entre componentes.

Ejemplos:

- Flask + MySQL.

- Backend + frontend.

- Autenticación + roles.

---

## Pruebas funcionales

Verifican que el sistema cumpla los requerimientos.

---

## Pruebas de regresión

Verifican que cambios nuevos no rompan funcionalidades existentes.

---

## Pruebas de seguridad

Buscan problemas relacionados con:

- Autenticación.

- Autorización.

- Validación.

- SQL Injection.

- XSS.

- CSRF.

- Sesiones.

- Información sensible.

---

# 4. Antes de una modificación

El equipo debe identificar:

- Qué funcionalidad será afectada.

- Qué pruebas existentes cubren esa funcionalidad.

- Qué nuevas pruebas podrían ser necesarias.

---

# 5. Después de una modificación

El equipo debe ejecutar las pruebas disponibles.

Debe informar:

- Pruebas ejecutadas.

- Resultado.

- Errores.

- Pruebas pendientes.

---

# 6. Registro de pruebas

| ID | Prueba | Requerimiento | Resultado | Fecha | Observaciones |

|---|---|---|---|---|---|

| TEST-001 | [Descripción] | RF-XXX | PASS/FAIL | DD/MM/AAAA | - |

---

# 7. Pruebas fallidas

Cuando una prueba falle:

1. Registrar el fallo.

2. Identificar causa probable.

3. Determinar si está relacionado con cambios recientes.

4. Corregir si corresponde.

5. Ejecutar nuevamente.

6. Registrar resultado final.

---

# 8. Regla

El equipo no debe afirmar que una funcionalidad está validada simplemente porque el código parece correcto.

Debe existir evidencia suficiente.
