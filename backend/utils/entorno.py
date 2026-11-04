"""Entorno de ejecución: desarrollo solo si se declara explícitamente.

Si falta FLASK_ENV (un .env incompleto en el servidor) se asume producción, no
desarrollo: así la aplicación se niega a arrancar sin SECRET_KEY propia en lugar
de iniciar con la clave de desarrollo, que es pública y permitiría falsificar una
sesión de administrador. En un equipo de desarrollo, `scripts/setup` escribe
FLASK_ENV=development en el .env y las pruebas lo fijan en tests/conftest.py.
"""
import os

ENTORNOS_DE_DESARROLLO = frozenset({"development", "dev", "testing", "test"})


def entorno_actual():
    return os.getenv("FLASK_ENV", "production").strip().lower()


def es_entorno_de_desarrollo():
    return entorno_actual() in ENTORNOS_DE_DESARROLLO


def es_produccion():
    return not es_entorno_de_desarrollo()
