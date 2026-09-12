# Sistema Web de Gestión Interna — Nahan Asesores

Proyecto de Ingeniería de Software I y II · Grupo 22 · Universidad Andrés Bello

Sistema web para la gestión interna de una empresa de servicios jurídicos y
contables: clientes, tareas, usuarios y roles, control de horas, reportes y
notificaciones.

## Puesta en marcha en un equipo nuevo

Necesitas **Python 3.9 o superior**, **MySQL 8** y **git**. Nada más.

```bash
git clone https://github.com/DaiTensh/nahan-asesores-sistema.git
cd nahan-asesores-sistema
```

Luego, según tu sistema:

```bash
bash scripts/setup.sh                                          # macOS y Linux
```
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1     # Windows
```

El instalador crea el entorno virtual, instala las dependencias, te pregunta los
datos de tu MySQL local, genera el `.env` con claves propias de tu máquina,
importa el esquema, carga datos de prueba y comprueba que la aplicación arranca.

El flujo normal puede repetirse: conserva una base existente y no vuelve a cargar
datos de prueba. La opción explícita `--solo-bd` recrea el esquema y puede borrar
los datos; no debe usarse para actualizar una instalación existente.
Cuando solo quieras poner al día las dependencias sin tocar nada más:

```bash
bash scripts/setup.sh --solo-deps                              # macOS y Linux
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 --solo-deps
```

Para levantar el sistema:

```bash
bash scripts/dev.sh                                            # macOS y Linux
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1       # Windows
```

El script imprime la dirección del frontend y la de la API, y abre el
navegador solo. Normalmente el frontend queda en
`http://127.0.0.1:5500/frontend/auth/login.html`; si ese puerto está tomado por
Live Server, el script usa el siguiente libre y te lo dice. Usa siempre esa
dirección: es la única que sabe en qué puerto quedó la API.

| | |
|---|---|
| Administrador | `renato.villalobos@nahan.local` |
| Área jurídica | `elias.alarcon@nahan.local` |
| Área contable | `carlos.castro@nahan.local` |
| Contraseña | `Nahan.2026` |

Son datos de desarrollo local, generados por `database/seed_dev.py`. No existen
en el servidor de producción.

> Los comandos se dan siempre a través de los envoltorios de `scripts/`. No es
> capricho: `python` a secas **no existe en macOS** —ahí solo está `python3`— y en
> Windows ocurre lo contrario. Los envoltorios buscan el intérprete correcto y,
> si el entorno virtual ya está creado, usan el suyo.

### Si algo falla

```bash
bash scripts/doctor.sh                                         # macOS y Linux
powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1    # Windows
```

Revisa una por una las condiciones que el sistema necesita y, por cada cosa que
falta, dice el comando exacto que la resuelve.

## Cómo se trabaja en el Incremento 2

El reparto de responsabilidades, los criterios de aceptación y las interfaces
compartidas están en [`docs/incremento2/README.md`](docs/incremento2/README.md).
Consulta la ficha del módulo correspondiente antes de modificarlo.

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
tests/              pruebas de regresión con pytest (bash scripts/test.sh)
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
  `http://127.0.0.1:5000/api`; en producción, a `/api` detrás de Nginx. En
  desarrollo, `scripts/dev.py` sirve una versión generada de ese archivo con el
  puerto que le tocó realmente a la API, sin modificar el del repositorio.
- **Producción**: Gunicorn + Nginx + systemd sobre una instancia EC2.

Las convenciones de código están en [`docs/development.md`](docs/development.md).

## Pruebas

```bash
bash scripts/test.sh                                           # macOS y Linux
powershell -ExecutionPolicy Bypass -File scripts\test.ps1       # Windows
```

Acepta los argumentos de pytest:

```bash
bash scripts/test.sh tests/test_rf26_restablecimiento.py -v
bash scripts/test.sh -k restablecimiento
```

`pytest` está en `requirements-dev.txt`, no en `requirements.txt`: es una
dependencia de desarrollo y el servidor no la instala. `scripts/setup.sh` la
instala junto con el resto.

## Advertencia

`.env` no se versiona y no debe versionarse: contiene las credenciales de tu
base de datos y las claves de sesión. Está en `.gitignore`.
