# Configuración de la base de datos local

Guía para dejar funcionando la base MySQL del proyecto en un equipo de desarrollo, desde cero o sobre una base que ya existe.

## 1. Problema que resuelve

Cada integrante necesita, en su equipo:

- un servidor MySQL corriendo;
- la base del proyecto con todas las tablas;
- las columnas y los parámetros que agregaron los incrementos posteriores.

**Antes**, el instalador (`scripts/setup.*`) solo creaba la base cuando no existía:

- si la base ya existía (por ejemplo, creada en el Incremento 1 o 2), se conservaba **sin aplicar las migraciones** de `database/migraciones/`;
- el sistema arrancaba y el diagnóstico decía «listo», pero las funciones nuevas fallaban. Ejemplo comprobado: sin la migración 005, `GET /api/historial` (RF56) responde 500;
- además, si la base se había creado a mano y estaba vacía, el instalador la conservaba sin tablas.

**Ahora**:

- el instalador crea la base si falta (o si existe vacía);
- aplica en orden las migraciones que le falten a una base existente, sin borrarla;
- carga los datos de prueba solo cuando la base es nueva;
- el diagnóstico (`scripts/doctor.*`) avisa si hay migraciones pendientes.

## 2. Cómo está estructurada la inicialización

| Pieza | Qué hace |
|---|---|
| `scripts/setup.ps1` (Windows) / `scripts/setup.sh` (macOS y Linux) | Buscan un Python 3.9+ y ejecutan `scripts/setup.py` |
| `scripts/setup.py` | Instalador: entorno virtual `.venv`, dependencias, archivo `.env`, base de datos, migraciones, datos de prueba y comprobación final |
| `database/nahan_asesores.sql` | Esquema completo vigente: 21 tablas, índices y datos base (roles, áreas, parámetros). Ya incluye lo de las migraciones 001–006 |
| `database/migraciones/NNN_*.sql` | Cambios para bases creadas antes de cada incremento: 001 `token_recuperacion`, 002 parámetros de adjuntos, 003 `documento.tipo_documento` + `uq_documento_referencia`, 004 `observacion_cliente`, 005 `auditoria.id_registro` + 3 índices, 006 parámetros de sesión |
| `database/migrar.py` | Revisa cada migración contra la base real (tablas, columnas, índices, parámetros) y ejecuta solo las que faltan. Si se repite, no hace nada |
| `database/seed_dev.py` | Datos de prueba: 7 usuarios del equipo, 6 clientes, 12 tareas, tarifas y registros de tiempo. Idempotente: no duplica lo que ya existe |
| `scripts/doctor.*` | Diagnóstico: Python, `.venv`, dependencias, `.env`, conexión con MySQL, base, migraciones, usuarios, puertos |

El flujo de `setup` en la parte de base de datos es el siguiente:

```
¿MySQL responde con los datos de .env?  ── no ─→ se detiene y explica qué revisar
        │ sí
¿Existe la base DB_NAME con tablas?
        ├─ no (no existe o está vacía) → importa database/nahan_asesores.sql (sin DROP)
        │                                → aplica migraciones (todas quedan «ya aplicada»)
        │                                → carga datos de prueba
        └─ sí → la conserva tal cual → aplica solo las migraciones pendientes
                                     → NO carga datos de prueba
Comprobación final: la API importa, responde en / y el login de prueba devuelve 200
```

## 3. Requisitos previos

- **Python 3.9 o superior.** En Windows, instálalo desde python.org marcando «Add Python to PATH».
- **MySQL Server 8** instalado y **corriendo**, más un usuario de MySQL con permiso para crear bases. Puede ser `root` o uno propio.
- **git** y el repositorio clonado.
- **Conexión a internet** en la primera ejecución, para instalar las dependencias de Python.

**No hace falta** que el cliente de consola `mysql` esté en el PATH. El instalador se conecta con el conector de Python. El cliente `mysql` solo sirve para las comprobaciones manuales de esta guía.

## 4. Nombre de la base y variables de entorno

La aplicación lee la conexión desde el archivo **`.env`** en la raíz del repositorio (`backend/config/db.py`).

- `.env` **no se sube a git**: está en `.gitignore`.
- La plantilla versionada es `.env.example`.
- La primera vez, `setup` crea `.env` preguntando los datos de MySQL.

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `DB_HOST` | `127.0.0.1` | Servidor MySQL |
| `DB_PORT` | `3306` | Puerto de MySQL |
| `DB_USER` | `root` | Usuario de MySQL |
| `DB_PASSWORD` | *(vacío)* | Contraseña de **tu** MySQL local. No se comparte ni se sube |
| `DB_NAME` | `nahan_asesores` | **Nombre de la base esperado por el proyecto** |

`setup` genera además `SECRET_KEY` y `JWT_SECRET` propios de tu equipo y completa el resto de claves de `.env.example` con valores de desarrollo. No hace falta tocarlas.

Para cambiar los datos de conexión más tarde, edita `.env` directamente. Si `DB_USER` y `DB_NAME` ya tienen valor, `setup` no vuelve a preguntar.

## 5. Comprobar MySQL antes de empezar

### Windows (PowerShell)

> Estos comandos son estándar de Windows. **No se ejecutaron en Windows en esta validación** (ver §11).

**1. ¿Está instalado el servicio y corriendo?**

```powershell
Get-Service *mysql*
```

- Muestra `Status`, `Name` y `DisplayName`. El `Name` depende de la instalación, por ejemplo `MySQL84` o `MySQL80`. Usa el que aparezca en **tu** equipo.
- Si no aparece nada, MySQL Server no está instalado como servicio. Instálalo con el instalador oficial de MySQL para Windows y vuelve a este paso.

**2. Si el `Status` es `Stopped`,** inícialo desde PowerShell **abierto como administrador**:

```powershell
Start-Service <Name que mostró Get-Service>
```

También puedes usar la aplicación «Servicios» (`services.msc`): busca el servicio de MySQL y pulsa «Iniciar».

**3. ¿Está el cliente `mysql` en el PATH?**

```powershell
mysql --version
```

Si responde «no se reconoce como un comando», el servidor puede estar instalado igual; solo falta el PATH. No es necesario para `setup`. Si lo quieres para las comprobaciones manuales, localiza la carpeta a partir del propio servicio (así no se supone ninguna ruta):

```powershell
Get-CimInstance Win32_Service -Filter "Name LIKE '%mysql%'" | Select-Object Name, State, PathName
```

`PathName` muestra la ruta de `mysqld.exe`. En esa misma carpeta `bin` está `mysql.exe`. Para usarlo solo en la ventana actual:

```powershell
$env:Path += ";<carpeta bin que mostró PathName>"
mysql --version
```

**4. ¿Se puede entrar con tu usuario?**

```powershell
mysql -u <tu_usuario> -p -e "SELECT VERSION();"
```

### macOS y Linux

```bash
mysql --version
brew services list | grep mysql      # macOS con Homebrew
brew services start mysql            # macOS: iniciar
sudo systemctl status mysql          # Linux con systemd
sudo systemctl start mysql           # Linux: iniciar
mysql -u <tu_usuario> -p -e "SELECT VERSION();"
```

### Error 2003 (10061 en Windows, 111 en Linux)

```
ERROR 2003 (HY000): Can't connect to MySQL server on 'localhost:3306' (10061)
```

Este error significa que **no hay un servidor MySQL escuchando** en ese host y puerto. **No es un error de contraseña:** la contraseña ni siquiera llega a comprobarse.

Revisa en este orden:

1. El servicio está iniciado (paso 1 de arriba).
2. El puerto es el correcto (`DB_PORT` en `.env`; 3306 por defecto).

Solo después de eso tiene sentido revisar el usuario y la contraseña.

El error de credenciales es otro:

```
1045 (28000): Access denied for user ...
```

Ese sí se corrige en `DB_USER` y `DB_PASSWORD` de `.env`.

## 6. Preparar la base: comando exacto

Desde la raíz del repositorio:

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

**macOS y Linux:**

```bash
bash scripts/setup.sh
```

La primera vez pregunta `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` (oculta) y `DB_NAME`. Enter acepta el valor entre corchetes.

El comando ejecuta los siguientes pasos:

1. Revisa la versión de Python.
2. Crea `.venv` si no existe e instala `requirements.txt` y `requirements-dev.txt`.
3. Crea o completa `.env` sin borrar lo que ya tenga.
4. Se conecta a MySQL. Si falla, se detiene con la explicación del error (2003 servicio / 1045 credenciales).
5. Base:
   - si no existe, o existe pero está vacía, importa `database/nahan_asesores.sql` **sin `DROP DATABASE`** (21 tablas);
   - si existe con tablas, **la conserva**.
6. Ejecuta `database/migrar.py`: revisa las migraciones 001–006 y aplica solo las que falten. En una base nueva todas figuran «ya aplicada».
7. Solo si la base es nueva: ejecuta `database/seed_dev.py` (datos de prueba).
8. Comprueba que la API arranca y que el login de prueba responde 200.

El comando se puede repetir las veces que haga falta: no borra la base ni duplica datos.

## 7. Comprobar que la base quedó bien

Diagnóstico completo:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\doctor.ps1     # Windows
```

```bash
bash scripts/doctor.sh                                          # macOS y Linux
```

Deben aparecer en `OK`: «Conexión con MySQL», «Base de datos: «nahan_asesores» con 21 tabla(s)», «Migraciones: todas aplicadas» y «Usuarios para iniciar sesión».

Solo las migraciones, sin modificar nada:

```powershell
.venv\Scripts\python.exe database\migrar.py --comprobar         # Windows
```

```bash
.venv/bin/python database/migrar.py --comprobar                 # macOS y Linux
```

Termina con `Base «nahan_asesores» al día con database/migraciones/.` Si falta algo, lista las migraciones `PENDIENTE` y sale con código 1.

Comprobación manual con el cliente `mysql`, si lo tienes:

```sql
USE nahan_asesores;
SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'nahan_asesores';  -- 21
SHOW COLUMNS FROM auditoria LIKE 'id_registro';                                          -- 1 fila
SELECT nombre_parametro FROM parametros_sistema WHERE nombre_parametro LIKE 'SESION_%';  -- 2 filas
```

## 8. Levantar la aplicación y confirmar la conexión con MySQL

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1        # Windows
```

```bash
bash scripts/dev.sh                                             # macOS y Linux
```

Antes de arrancar, `dev` abre una conexión real con MySQL usando `.env`. Si no puede, se detiene y muestra el error de conexión. Luego imprime las direcciones de la API y del frontend.

Para confirmar que la aplicación está usando MySQL:

1. Inicia sesión en el frontend con `renato.villalobos@nahan.local` y la contraseña de desarrollo `Nahan.2026`. Esa cuenta existe solo en la base local creada por `seed_dev.py`. El login lee la tabla `usuario`: si entra, la API está leyendo MySQL.
2. Como administrador, abre «Historial de actividad». Si carga sin error, la migración 005 está aplicada.

La ruta `http://127.0.0.1:5000/` («API Nahan Asesores funcionando correctamente») solo confirma que Flask arrancó; **no** consulta MySQL.

## 9. Si la base ya existe

- **Uso normal:** ejecuta el mismo comando de §6. La base se conserva con todos sus datos, recibe solo las migraciones que le falten y no se le cargan datos de prueba.
- **Faltan los datos de prueba** (por ejemplo, no hay usuarios para entrar): ejecuta `powershell -ExecutionPolicy Bypass -File scripts\seed.ps1` (Windows) o `bash scripts/seed.sh` (macOS y Linux). Es idempotente: agrega lo que falta sin duplicar.
- **Opciones que BORRAN datos**, que no son necesarias para preparar ni actualizar la base:
  - `setup --solo-bd` recrea la base completa: pide confirmación si hay datos y, con `--si-a-todo`, borra sin preguntar;
  - `seed --reset` elimina y vuelve a crear los datos de prueba: usuarios `@nahan.local`, clientes de ejemplo y los registros asociados (tareas, registros de tiempo, notificaciones, reportes y auditoría de esos usuarios).

  Úsalas solo si decides descartar tu base local.

## 10. Errores comunes

| Síntoma | Causa | Solución |
|---|---|---|
| `2003 (HY000): Can't connect to MySQL server on '…:3306' (10061)` | El servicio MySQL no está corriendo o el puerto no es ese | Iniciar el servicio (§5); revisar `DB_PORT`. No cambies la contraseña por este error |
| `1045 (28000): Access denied for user …` | Usuario o contraseña incorrectos | Corregir `DB_USER` / `DB_PASSWORD` en `.env` y repetir `setup` |
| `mysql` «no se reconoce como un comando» | El cliente no está en el PATH | No afecta a `setup`. Para las pruebas manuales, ver §5 paso 3 |
| `doctor` muestra «Migraciones: pendientes: 005, 006» | Base de un incremento anterior | Ejecutar `setup` (§6) |
| El historial de actividad da error 500 | Falta la migración 005 (`auditoria.id_registro`) | Ejecutar `setup` (§6) |
| `setup` se detiene en «Las migraciones no terminaron» | Una sentencia falló por un motivo distinto de «ya existe». Ejemplo: la 003 no puede crear `uq_documento_referencia` si hay documentos repetidos | La base no se borra. Corregir el dato indicado en el mensaje y repetir `setup` |
| PowerShell no deja ejecutar el script | Política de ejecución | Usar exactamente `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1` |
| «No encontré un Python 3.9 o superior» | Python no instalado o fuera del PATH | Instalar Python marcando «Add Python to PATH» |

## 11. Pruebas realizadas

Ambiente de validación de la base: Ubuntu 24.04, **MySQL Server 8.0.46**, Python 3.13, scripts `.sh`, usuario MySQL de prueba. Suite de pruebas: Linux, Python 3.10.

| Prueba | Resultado |
|---|---|
| Base ausente → `setup` | Crea 21 tablas, migraciones 001–006 «ya aplicada», siembra 7 usuarios / 6 clientes / 12 tareas; login 200 |
| Repetir `setup` sobre esa base | Base conservada; conteos idénticos (7 / 6 / 12 / 7 registros de tiempo / 8 parámetros); sin duplicados |
| Base creada a mano y vacía → `setup` | Detecta «existe pero está vacía», crea las 21 tablas y siembra |
| Base «antigua» sin 001–006 (tablas, columna, índices y parámetros retirados) con un cliente propio → `setup` | Aplica 001–006; el cliente propio y los 7 usuarios siguen ahí; columnas resultantes idénticas a una base nueva; la 005 recupera `id_registro` desde el texto de auditoría |
| Base sin 005/006 → `doctor` / `migrar --comprobar` | Informan «pendientes: 005, 006» (código de salida 1); después de `setup`, «todas aplicadas» |
| `GET /api/historial` antes y después de migrar | 500 → 200 |
| Servidor detenido → `setup`, `doctor`, `dev` | `setup` y `doctor` explican que es el servicio y no la contraseña; `dev` no arranca y muestra el error 2003 |
| Contraseña incorrecta → `setup`, `doctor` | Mensaje específico de credenciales (1045) |
| `seed` repetido | «Ya existía: …»; no duplica |
| `dev --api --sin-navegador` + `POST /api/login` + `GET /api/historial` | 200 / 200 |
| Suite `pytest` completa (Python 3.10, sobre el repositorio con los cambios) | **347 aprobadas, 0 fallidas**, incluido `tests/test_preparacion_bd.py` (nuevo). Las pruebas no requieren MySQL |

**No validado:**

- **Windows y MySQL 8.4.** Los comandos de PowerShell de §5 son estándar de Windows, pero no se ejecutaron. `setup.ps1` no se modificó y solo delega en `setup.py`, que es el mismo en los tres sistemas.
- **macOS:** usa los mismos scripts `.sh` y `setup.py`, pero no se ejecutó en esta validación.
- **Creación interactiva de `.env`** (las preguntas por teclado): la lógica no se modificó; la validación usó un `.env` ya creado.

## 12. Limitaciones conocidas

- `migrar.py` reconoce cada migración por su efecto en la base (tabla, columna, índice o parámetro). No existe una tabla de control de versiones, para no agregar tablas al modelo de datos.
- Una migración nueva (007 en adelante) se agrega como `database/migraciones/NNN_nombre.sql` y **debe registrarse en `MARCADORES`** de `database/migrar.py`, indicando cómo se reconoce que ya está aplicada (tabla, columna, índice o parámetro). `tests/test_preparacion_bd.py` falla si una migración no tiene marcador. Aun así conviene escribirla para que repetirla no cause daño (`CREATE TABLE IF NOT EXISTS`, `INSERT IGNORE`, etc.): una sentencia que falle por «ya existe» (tabla, columna, índice o clave foránea) se omite, y cualquier otro error detiene el proceso sin borrar nada.
- En una base migrada desde la 001, el índice de la clave foránea de `token_recuperacion` puede quedar con otro nombre que en una base nueva. No cambia el funcionamiento.
- `setup` no instala ni configura el servidor MySQL: eso se hace una vez, con el instalador oficial.

## 13. Archivos de este mecanismo

| Archivo | Cambio |
|---|---|
| `database/migrar.py` | **Nuevo.** Aplica o comprueba las migraciones pendientes |
| `scripts/setup.py` | Llama a `migrar.py` en cada ejecución; importa el esquema cuando la base existe vacía; mensajes separados para 2003 y 1045 |
| `scripts/doctor.py` | Nuevo chequeo «Migraciones»; mensajes separados para 2003 y 1045 |
| `tests/test_preparacion_bd.py` | **Nuevo.** Pruebas del mecanismo sin MySQL |
| `tests/test_incremento1_regression.py` | Ajuste de una aserción: la importación usa ahora `CREATE DATABASE IF NOT EXISTS` |
| `README.md` | Menciona las migraciones y enlaza esta guía |
| `docs/setup/CONFIGURACION_BASE_DATOS.md` | **Nuevo.** Esta guía |
