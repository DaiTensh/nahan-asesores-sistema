# Sistema Web de Gestión Interna — Nahan Asesores

Proyecto de Ingeniería de Software I y II · Grupo 22 · Universidad Andrés Bello

Sistema web para la gestión interna de una empresa de servicios jurídicos y
contables: clientes, tareas, usuarios y roles, control de horas, reportes y
notificaciones.

## Puesta en marcha en un equipo nuevo

Necesitas **Python 3.10 o superior**, **MySQL 8** y **git**. Nada más.

```bash
git clone https://github.com/DaiTensh/nahan-asesores-sistema.git
cd nahan-asesores-sistema
```

Luego, según tu sistema:

```bash
bash scripts/setup.sh              # macOS y Linux
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1    # Windows
python scripts/setup.py            # cualquiera de los tres
```

El instalador crea el entorno virtual, instala las dependencias, te pregunta los
datos de tu MySQL local, genera el `.env` con claves propias de tu máquina,
importa el esquema, carga datos de prueba y comprueba que la aplicación arranca.
Se puede volver a ejecutar las veces que haga falta.

Para levantar el sistema:

```bash
python scripts/dev.py
```

Y se abre en `http://127.0.0.1:5500/frontend/auth/login.html`.

| | |
|---|---|
| Administrador | `renato.villalobos@nahan.local` |
| Área jurídica | `elias.alarcon@nahan.local` |
| Área contable | `carlos.castro@nahan.local` |
| Contraseña | `Nahan.2026` |

Son datos de desarrollo local, generados por `database/seed_dev.py`. No existen
en el servidor de producción.

### Si algo falla

```bash
python scripts/doctor.py
```

Revisa una por una las condiciones que el sistema necesita y, por cada cosa que
falta, dice el comando exacto que la resuelve.

## Cómo se trabaja en el Incremento 2

Instala [Claude Code](https://claude.com/claude-code), ábrelo en esta carpeta y
di tu nombre:

```
hola, soy Renato
```

Claude te identifica, revisa el entorno, instala lo que falte, crea tu rama, lee
los requerimientos que te tocan y empieza a programarlos contigo. El reparto
completo está en [`docs/incremento2/README.md`](docs/incremento2/README.md).

## Estructura

```
backend/            API en Flask, un blueprint por módulo en routes/
  config/db.py      conexión a MySQL
  utils/            autenticación y hash de contraseñas
frontend/           HTML, CSS y JavaScript sin frameworks, una carpeta por módulo
database/           esquema (nahan_asesores.sql) y datos de prueba (seed_dev.py)
scripts/            instalador, diagnóstico y arranque
deploy/             unidades de systemd y configuración de Nginx para el EC2
docs/               arquitectura, convenciones, decisiones y reparto del incremento
tests/              pruebas de regresión con pytest
```

## Arquitectura

- **Backend**: Python + Flask, organizado en blueprints registrados en
  `backend/app.py` con prefijo `/api`.
- **Acceso a datos**: `mysql-connector-python` a través de `get_connection()`.
  SQL siempre parametrizado.
- **Autenticación**: sesión por cookie de Flask. Decoradores `login_required` y
  `roles_required(*roles)` en `backend/utils/auth.py`. Roles: `ADMINISTRADOR`,
  `USUARIO_AREA_JURIDICA`, `USUARIO_AREA_CONTABLE`.
- **Frontend**: HTML, CSS y JavaScript puro. `frontend/assets/js/api_config.js`
  decide la URL de la API según el origen: servido desde el puerto 5500 apunta a
  `http://127.0.0.1:5000/api`; en producción, a `/api` detrás de Nginx.
- **Producción**: Gunicorn + Nginx + systemd sobre una instancia EC2.

Las convenciones de código están en [`docs/development.md`](docs/development.md)
y las reglas de trabajo con Claude en [`CLAUDE.md`](CLAUDE.md).

## Pruebas

```bash
python -m pytest
```

## Advertencia

`.env` no se versiona y no debe versionarse: contiene las credenciales de tu
base de datos y las claves de sesión. Está en `.gitignore`.
