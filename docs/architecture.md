# Arquitectura del Sistema

## 1. Propósito

Este documento describe la arquitectura técnica del sistema desarrollado para Nahan Asesores.

Debe mantenerse alineado con la Dimensión Técnica oficial y con la implementación real del proyecto.

---

# 2. Arquitectura general

La aplicación utiliza una arquitectura web compuesta principalmente por:

```text
Usuario
   ↓
Nginx
   ↓
Gunicorn
   ↓
Flask
   ↓
Lógica de aplicación
   ↓
MySQL 8
