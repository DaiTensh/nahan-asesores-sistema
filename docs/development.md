# Guía de Desarrollo

## 1. Propósito

Este documento define las convenciones utilizadas para desarrollar y mantener el proyecto.

Claude debe consultar este documento antes de realizar modificaciones importantes.

---

# 2. Principios

El desarrollo debe priorizar:

- Código claro.
- Simplicidad.
- Mantenibilidad.
- Seguridad.
- Reutilización.
- Separación de responsabilidades.
- Compatibilidad con la arquitectura existente.

---

# 3. Backend

Tecnología:

- Python.
- Flask.

Las modificaciones deben respetar la estructura existente.

Evitar:

- Duplicación innecesaria.
- Funciones excesivamente grandes.
- Lógica difícil de mantener.
- Código sin validaciones.
- Manejo deficiente de errores.

---

# 4. Frontend

Tecnologías:

- HTML.
- CSS.
- JavaScript.

No incorporar frameworks frontend sin autorización.

Priorizar:

- Reutilización.
- Consistencia.
- Accesibilidad.
- Validación.
- Código comprensible.

---

# 5. Base de datos

Motor:

MySQL 8.

Antes de cambiar la base de datos se debe revisar la documentación oficial.

Las modificaciones deben considerar:

- Integridad referencial.
- Claves.
- Restricciones.
- Datos existentes.
- Compatibilidad con el backend.

---

# 6. Git

Las funcionalidades nuevas deben desarrollarse en branches.

Ejemplos:

```text
feature/nombre-funcionalidad
feature/RF-XXX
fix/nombre-problema
docs/nombre-documentacion
