# Guía de instalación local — Nahan Asesores

Guía para preparar una instalación local desde un clon nuevo. La aplicación
usa Flask, MySQL 8 y un frontend estático HTML/CSS/JavaScript. Los comandos de
Windows se ejecutan en PowerShell; los de macOS, en Terminal.

## 1. Requisitos previos

- Git.
- Python 3.9 o superior.
- MySQL Server 8 en ejecución y una cuenta que pueda crear la base de datos.
- Conexión a Internet durante la primera instalación de dependencias.
- Un navegador actualizado.

Node.js no es necesario para ejecutar el sistema. Algunas pruebas del frontend
lo detectan opcionalmente.

### Instalar las herramientas

- **Windows:** instala Git desde [git-scm.com](https://git-scm.com/downloads) y
  Python desde [python.org](https://www.python.org/downloads/). Al instalar
  Python, activa **Add Python to PATH**. Instala MySQL Server 8 con el
  instalador oficial de MySQL; conserva el nombre del servicio que el
  instalador muestre.
- **macOS:** instala Git con las herramientas de línea de comandos de Xcode
  (`xcode-select --install`) o desde Git. Instala Python 3.9+ desde
  [python.org](https://www.python.org/downloads/) o un gestor de paquetes.
  Instala MySQL Server 8 y confirma que `mysql --version` indica la serie 8.
  Si se instaló con Homebrew, el servicio puede iniciarse con
  `brew services start mysql`.

El proyecto requiere MySQL 8; no se presupone que una instalación nueva de un
gestor de paquetes instale esa versión principal. Confirma la versión antes
de continuar. En Windows, `Get-Service *mysql*` muestra el servicio instalado;
si está detenido, inicia el servicio MySQL desde Servicios de Windows o desde
PowerShell como administrador con `Start-Service <nombre-del-servicio>`.

## 2. Clonar el repositorio

Abre PowerShell o Terminal, elige una carpeta de trabajo y ejecuta:

**Windows (PowerShell):**

```powershell
git clone https://github.com/DaiTensh/nahan-asesores-sistema.git
Set-Location nahan-asesores-sistema
```

**macOS:**

```bash
git clone https://github.com/DaiTensh/nahan-asesores-sistema.git
cd nahan-asesores-sistema
```

Ejecuta los pasos siguientes desde la raíz del repositorio.

## 3. Crear el entorno, configurar MySQL e inicializar usuarios

El instalador oficial del proyecto configura el entorno virtual `.venv`,
instala `requirements.txt` y `requirements-dev.txt`, pregunta los datos de
MySQL, genera `.env`, prepara el esquema, aplica migraciones pendientes y
verifica que la aplicación arranque.

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

**macOS:**

```bash
bash scripts/setup.sh
```

Ingresa el host, puerto, usuario y contraseña de **tu MySQL local** cuando el
instalador lo solicite. La contraseña se solicita sin mostrarla. La base
predeterminada es `nahan_asesores`. El instalador crea una `SECRET_KEY` local;
`.env` queda excluido de Git.

En una base inexistente o vacía, el instalador crea e importa el esquema y
carga usuarios y datos de desarrollo. Si la base ya tiene tablas, la conserva,
aplica únicamente las migraciones pendientes y no vuelve a sembrar los datos.
El proceso normal no ejecuta el `DROP DATABASE` presente en
`database/nahan_asesores.sql`. **No importes ese archivo directamente con
`mysql < ...` ni ejecutes `setup --solo-bd`:** esa opción está destinada a una
recreación explícita y puede borrar datos.

El sembrado define cuentas de demostración con una contraseña pública en
`database/seed_dev.py`. Esas cuentas y contraseña son solo para desarrollo
local; no expongas el servidor ni reutilices esa contraseña en producción. Para
una base nueva, `seed_dev.py` admite la variable de proceso
`NAHAN_SEED_PASSWORD`. Puede proporcionarse antes del primer sembrado sin
escribirla en el historial del shell:

**Windows (PowerShell):**

```powershell
$secreto = Read-Host "Contraseña inicial local única" -AsSecureString
$puntero = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secreto)
try {
    $env:NAHAN_SEED_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($puntero)
    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
}
finally {
    Remove-Item Env:NAHAN_SEED_PASSWORD -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($puntero)
    $secreto.Dispose()
}
```

**macOS (bash):**

```bash
read -s -p "Contraseña inicial local única: " NAHAN_SEED_PASSWORD
printf '\n'
export NAHAN_SEED_PASSWORD
bash scripts/setup.sh
unset NAHAN_SEED_PASSWORD
```

El valor se transmite al sembrador como variable de proceso y se elimina al
terminar. Usa una contraseña exclusiva para este entorno y no la escribas en
el repositorio ni en `.env`. La variable solo afecta un sembrado nuevo; no
cambia claves de usuarios de una base existente. Si omites la variable, trata
las cuentas sembradas como credenciales públicas de prueba.

El instalador solo siembra automáticamente cuando crea la base. Para agregar
datos de desarrollo a una base local existente, el repositorio ofrece
`bash scripts/seed.sh` en macOS o
`powershell -ExecutionPolicy Bypass -File scripts\seed.ps1` en Windows. No
ejecutes la siembra en producción.

### Archivo `.env`

El instalador genera `.env` a partir de `.env.example` y conserva los valores
existentes. Entre las variables relevantes están `DB_HOST`, `DB_PORT`,
`DB_USER`, `DB_PASSWORD`, `DB_NAME`, `SECRET_KEY`, `FLASK_ENV`,
`APP_TIMEZONE`, `SESSION_COOKIE_*` y `ALLOWED_ORIGINS`. No publiques ni copies
el archivo a un issue o chat. Si ya existe, revisa su configuración local sin
mostrar la contraseña. La plantilla no reemplaza los valores de una
instalación ya configurada.

## 4. Comprobar la instalación

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1
```

**macOS:**

```bash
bash scripts/doctor.sh
```

El diagnóstico comprueba Python, entorno virtual, dependencias, `.env`,
conexión con MySQL, esquema, migraciones y datos de acceso. Para comprobar
solo las migraciones sin aplicarlas:

```text
Windows: .venv\Scripts\python.exe database\migrar.py --comprobar
macOS:   .venv/bin/python database/migrar.py --comprobar
```

## 5. Iniciar backend y frontend

El lanzador del proyecto inicia el backend Flask y el servidor estático del
frontend. Elige puertos libres, configura el origen de API y muestra las URL
efectivas; no presupongas que serán siempre `5000` y `5500`.

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

**macOS:**

```bash
bash scripts/dev.sh
```

Abre en el navegador la URL del login que imprime el lanzador. Para ejecutar
solo la API, usa `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
--api` en Windows o `bash scripts/dev.sh --api` en macOS.

### Comando correcto de Flask y error `No module named 'backend'`

El paquete `backend` está en la raíz del repositorio. El directorio actual
debe ser esa raíz para que Python pueda importarlo. El comando soportado para
ejecutar solo la API con el entorno virtual activo es:

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
python -m backend.app
```

**macOS:**

```bash
source .venv/bin/activate
python -m backend.app
```

No uses `python backend/app.py`: al ejecutar un archivo por ruta, Python
antepone `backend/` al camino de importación y no garantiza que encuentre el
paquete raíz `backend`. También puedes evitar activar el entorno:

```text
Windows: .venv\Scripts\python.exe -m backend.app
macOS:   .venv/bin/python -m backend.app
```

Estos comandos arrancan solo la API; para usar las pantallas, inicia ambos
procesos con `scripts/dev`. `python -m backend.app` toma `FLASK_RUN_HOST` y
`FLASK_RUN_PORT` del entorno y, por omisión, escucha en `127.0.0.1:5000`.
El lanzador de desarrollo gestiona los puertos y el frontend por ti.

## 6. Comprobaciones funcionales

En la interfaz local, comprueba:

1. Inicio de sesión con una cuenta local activa.
2. Carga del dashboard y navegación a clientes, tareas y control de horas.
3. Inicio y detención de un temporizador en una tarea disponible.
4. Aparición del registro cerrado en el historial y actualización de totales.
5. Acceso de administrador al informe de horas y a sus exportaciones.
6. Cierre de sesión.

El registro manual de horas **no está implementado**: su especificación está
bloqueada por decisiones de negocio pendientes. El control de horas actual
registra tiempo mediante el temporizador.

## 7. Ejecutar pruebas

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
```

**macOS:**

```bash
bash scripts/test.sh
```

Las pruebas con MySQL real usan servidores desechables locales cuando las
herramientas requeridas están disponibles; no configures una base productiva
para ejecutar la suite. Usa `scripts/test.sh` (macOS) o `scripts\test.ps1`
(Windows) para pasar selectores de pytest.

## 8. Detener y reiniciar

- Detén backend y frontend con **Ctrl+C** en la terminal que ejecuta
  `scripts/dev`.
- Para reiniciar, ejecuta de nuevo el mismo comando. Los datos se mantienen
  en MySQL.
- Si el servicio MySQL está detenido, inícialo con el servicio del sistema
  operativo y vuelve a ejecutar `scripts/dev`.

## 9. Solución de problemas frecuentes

| Síntoma | Causa probable y acción |
|---|---|
| `ModuleNotFoundError: No module named 'backend'` | Cambia a la raíz del clon y ejecuta `python -m backend.app` o usa `scripts/dev`; no ejecutes `python backend/app.py`. |
| `No encontré un Python 3.9 o superior` | Instala Python 3.9+ y asegúrate de que el ejecutable esté disponible en PATH. |
| Error MySQL `2003` o `2002` | El servicio no escucha en el host/puerto configurado. Inicia MySQL y revisa `DB_HOST`/`DB_PORT` en `.env`; no es un error de contraseña. |
| Error MySQL `1045` | Usuario o contraseña incorrectos. Corrige `DB_USER`/`DB_PASSWORD` en `.env` y vuelve a ejecutar el instalador. |
| El diagnóstico indica migraciones pendientes | Ejecuta el instalador normal; conserva una base existente y aplica migraciones pendientes. Revisa antes el resultado de `doctor`. |
| No puedes iniciar sesión en una base preexistente | El instalador no siembra cuentas sobre una base que ya tiene tablas. Comprueba con el administrador de esa base; no ejecutes `--solo-bd` ni `seed --reset`. |
| PowerShell bloquea el script | Usa el comando indicado con `-ExecutionPolicy Bypass`; no hace falta cambiar permanentemente la política del equipo. |
| No aparecen las URL esperadas | Usa las direcciones impresas por `scripts/dev`; sus puertos pueden cambiar si los habituales están ocupados. |

Para obtener un diagnóstico detallado, vuelve a ejecutar `scripts/doctor`
con el envoltorio correspondiente a tu sistema operativo. No compartas `.env`
ni salidas que incluyan credenciales.
