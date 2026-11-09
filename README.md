# Nahan Asesores — Sistema Web de Gestión Interna

Proyecto de Ingeniería de Software I y II · Grupo 22 · Universidad Andrés Bello

Nahan Asesores es una empresa de servicios jurídicos y contables. Este sistema
web reemplaza la gestión manual de su operación diaria: concentra clientes,
tareas, usuarios, control de horas, reportes y avisos en una sola aplicación,
con acceso según el rol de cada persona.

## Qué hace el sistema

- **Clientes**: registro, edición, estados, asignación a áreas, ficha del
  cliente con observaciones y referencias documentales, búsqueda avanzada y
  exportación a Excel.
- **Tareas**: creación, asignación y reasignación, prioridades, estados,
  adjuntos, flujo de revisión (envío, aprobación y rechazo por un
  administrador).
- **Usuarios y roles**: administrador, usuario del área jurídica y usuario del
  área contable; alta, edición, desactivación, cambio de rol y recuperación de
  contraseña.
- **Control de horas y cobros**: temporizador por tarea, registro manual de
  horas ya trabajadas (botón «Registrar horas manualmente»; CU-14 y CU-29),
  tarifa general y por área definidas por el administrador (RF74), cálculo de
  montos y reporte de cobro por cliente con período opcional, desglose por
  tarifa y exportación (RF75). El registro manual guarda su origen y una
  observación, se limita a los últimos 30 días, no admite horas futuras ni
  solapes con otras horas del mismo usuario y entra solo a los totales,
  al informe de horas y al cobro; requiere la migración 012. El detalle de cada
  tarea incluye la sección «Horas trabajadas» (totales, historial y los botones
  para iniciar el temporizador o registrar horas, RF71, RF73, CU-14 y CU-29).
- **Dashboard y reportes**: indicadores de tareas pendientes, vencidas y
  finalizadas, carga por usuario, distribución por área, reportes por cliente,
  responsable y área, exportación a PDF y Excel.
- **Notificaciones**: avisos con importancia (normal, alta o crítica), campana
  con contador y aviso de vencimientos.
- **Auditoría e historial**: registro de accesos y modificaciones, historial
  global filtrable (solo administradores) e historial por cliente.
- **Búsqueda global** de clientes, tareas y usuarios, y **cierre automático de
  sesión por inactividad** configurable.
- **Respaldos (RF60)**: respaldo diario programado y manual de la base de datos
  y los adjuntos, historial de cada ejecución y restauración controlada, solo
  para administradores (detalles en `docs/RF60_INFORME_IMPLEMENTACION.md`).

## Tecnologías

- **Backend**: Python y Flask, con un blueprint por módulo bajo el prefijo
  `/api`. Autenticación por sesión (cookie de Flask) y contraseñas con bcrypt.
- **Base de datos**: MySQL 8, a través de `mysql-connector-python`.
- **Frontend**: HTML, CSS y JavaScript sin frameworks.
- **Exportaciones**: openpyxl (Excel) y reportlab (PDF).
- **Pruebas**: pytest.
- **Producción**: Gunicorn, Nginx y systemd sobre una instancia EC2 de AWS.

## Requisitos previos

- **Python 3.9 o superior**.
- **MySQL Server 8**, instalado y en ejecución, y un usuario de MySQL con
  permiso para crear bases de datos (por ejemplo, `root`).
- **git**.

## Puesta en marcha

### 1. Clonar el repositorio

```bash
git clone https://github.com/DaiTensh/nahan-asesores-sistema.git
cd nahan-asesores-sistema
```

### 2. Instalar y configurar (un solo comando)

```bash
bash scripts/setup.sh                                          # macOS y Linux
```
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1     # Windows
```

El instalador:

1. crea el entorno virtual `.venv` e instala las dependencias de
   `requirements.txt` y `requirements-dev.txt`;
2. te pregunta los datos de tu MySQL local y genera el archivo `.env` con
   claves propias de tu equipo (la plantilla es `.env.example`);
3. crea la base de datos `nahan_asesores` a partir de
   `database/nahan_asesores.sql` (24 tablas) y aplica las migraciones de
   `database/migraciones/` que falten;
4. carga datos de demostración (`database/seed_dev.py`);
5. comprueba que la aplicación arranca.

Es repetible: si la base ya existe la conserva y solo aplica las migraciones
pendientes. Opciones útiles: `--solo-deps` (solo dependencias), `--sin-datos`
(no cargar datos de demostración) y `--si-a-todo` (no preguntar).

> **Cuidado:** `database/nahan_asesores.sql` comienza con
> `DROP DATABASE IF EXISTS nahan_asesores`. No lo importes a mano sobre una base
> con datos; usa siempre `scripts/setup`.

#### Instalación manual (alternativa)

```bash
python3 -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                       # Windows: copy .env.example .env
```

Edita `.env` con los datos de tu MySQL (`DB_USER`, `DB_PASSWORD`; el nombre
esperado de la base es `nahan_asesores`) y una `SECRET_KEY` propia. Después
ejecuta `scripts/setup`: reutiliza el entorno virtual y el `.env` existentes y
se encarga de la base de datos.

### 3. Configuración (`.env`)

`.env` **no se versiona** (está en `.gitignore`). `.env.example` documenta cada
variable que usa el sistema: conexión a MySQL, `SECRET_KEY`, cookies de
sesión, correo SMTP opcional (si se deja vacío, el enlace de restablecimiento
de contraseña se registra en el log), carpeta de adjuntos y tamaño máximo de
solicitudes y, desde el Incremento 4, la carpeta de respaldos (`RESPALDO_DIR`) y
la habilitación de la restauración. Nunca subas un `.env` real al repositorio.

### 4. Ejecutar la aplicación

```bash
bash scripts/dev.sh                                            # macOS y Linux
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1       # Windows
```

El script levanta la API y el frontend, imprime ambas direcciones y abre el
navegador. Normalmente el frontend queda en
`http://127.0.0.1:5500/frontend/auth/login.html`; si ese puerto está ocupado
usa el siguiente libre. Usa siempre la dirección que imprime.

### 5. Usuarios de demostración

| Rol | Correo |
|---|---|
| Administrador | `renato.villalobos@nahan.local` |
| Usuario área jurídica | `elias.alarcon@nahan.local` |
| Usuario área contable | `carlos.castro@nahan.local` |

La contraseña de todos es la que define `database/seed_dev.py` (`PASSWORD_DEV`). Son
**credenciales exclusivas del entorno local de desarrollo**, generadas por ese script:
no deben existir en un servidor ni reutilizarse fuera de un equipo de desarrollo. Si
alguna llegó a un servidor, `python database/rotar_cuentas_demo.py` informa cuáles
siguen aceptándola y, con `--aplicar`, las rota o las desactiva.

### Si algo falla

```bash
bash scripts/doctor.sh                                         # macOS y Linux
powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1    # Windows
```

Revisa una por una las condiciones que necesita el sistema (Python, entorno
virtual, dependencias, `.env`, MySQL, base, migraciones, puertos) y, por cada
una que falta, indica el comando que la resuelve.

> Los comandos se dan siempre a través de los envoltorios de `scripts/`:
> en macOS solo existe `python3` y en Windows `python`, y los envoltorios
> buscan el intérprete correcto y usan el del entorno virtual si existe.

## Pruebas

```bash
bash scripts/test.sh                                           # macOS y Linux
powershell -ExecutionPolicy Bypass -File scripts\test.ps1      # Windows
```

Acepta los argumentos de pytest, por ejemplo:

```bash
bash scripts/test.sh tests/test_rf26_restablecimiento.py -v
bash scripts/test.sh -k historial
```

La suite (`tests/`, 1.879 casos en esta revisión) no usa tu base de datos real: trabaja con conexiones
simuladas, con una base SQLite temporal o, en las pruebas marcadas «MySQL real», con un
`mysqld` propio y desechable en un puerto efímero que se borra al terminar (necesita
`mysqld` y `mysqldump` instalados; sin ellos esas pruebas se omiten). Cubre autenticación,
autorización por rol, auditoría, flujo de revisión de tareas, notificaciones, reportes y
exportaciones, respaldos y las reglas de cada requisito funcional. `pytest` está en
`requirements-dev.txt`: es una dependencia de desarrollo y el servidor no la instala.

Última ejecución completa, el 8-nov-2026 en macOS con Python 3.9.6: **1.865 aprobadas,
14 omitidas y 0 fallidas**. Las omitidas requieren un volumen distinto y `mysqldump`
para RF60, o un puerto de MySQL desechable solicitado expresamente para SEC-02; el mismo
día se ejecutaron con ambas variables y pasaron las 14.

Por defecto quedan 14 pruebas omitidas, que se activan a propósito: 5 de RF60 con
`NAHAN_TEST_OTRO_DISPOSITIVO=<carpeta de un volumen distinto del disco de la aplicación>` y 9 del
límite de inicios de sesión con `NAHAN_TEST_MYSQL_PORT=<puerto de un MySQL local desechable>`.
Referencia histórica del 5-nov-2026 (Python 3.9, macOS): 1.723 correctas y ninguna
omitida con ambas variables; 1.709 correctas y 14 omitidas con la configuración por defecto.

## Estructura del proyecto

```
backend/            API en Flask, un blueprint por módulo en routes/
  config/db.py        conexión a MySQL
  utils/              autenticación, hash de contraseñas, auditoría y correo
  tareas_programadas.py   aviso de vencimientos (proceso programado)
frontend/           HTML, CSS y JavaScript sin frameworks, una carpeta por módulo
database/           esquema (nahan_asesores.sql), migraciones, migrar.py y seed_dev.py
scripts/            instalador, diagnóstico, arranque y pruebas
deploy/             Nginx y unidades de systemd para el servidor
docs/               documentación técnica y de despliegue
tests/              pruebas automáticas con pytest
```

## Documentación adicional

- [`docs/GUIA_INSTALACION_LOCAL.md`](docs/GUIA_INSTALACION_LOCAL.md):
  instalación y ejecución local en Windows y macOS.
- [`docs/GUIA_DESPLIEGUE_AWS.md`](docs/GUIA_DESPLIEGUE_AWS.md):
  operación basada en la configuración versionada y puntos que se deben
  confirmar en AWS.
- [`docs/architecture.md`](docs/architecture.md): arquitectura general.
- [`docs/setup/CONFIGURACION_BASE_DATOS.md`](docs/setup/CONFIGURACION_BASE_DATOS.md):
  guía detallada de MySQL y de las migraciones (incluye Windows).
- [`docs/development.md`](docs/development.md): convenciones de código.
- [`docs/design-system.md`](docs/design-system.md): criterios visuales del frontend.
- [`docs/deploy_aws_demo.md`](docs/deploy_aws_demo.md): despliegue en AWS EC2.
- [`docs/incremento2/`](docs/incremento2/README.md): fichas de trabajo del
  Incremento 2 (referencia histórica).

## Despliegue

El sistema se desplegó en una instancia EC2 con Ubuntu, MySQL local, Gunicorn,
Nginx y systemd. Los archivos de configuración están en `deploy/` y el
procedimiento completo, en [`docs/deploy_aws_demo.md`](docs/deploy_aws_demo.md).
En el servidor el proyecto vive en `/var/www/nahan-asesores-sistema`.

## Seguridad

`.env` contiene credenciales y claves de sesión: no se versiona y no debe
versionarse. En producción `SECRET_KEY` es obligatoria (la aplicación no
arranca sin ella) y las cookies de sesión se configuran desde `.env`.
