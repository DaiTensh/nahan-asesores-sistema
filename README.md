# Nahan Asesores Sistema
Sistema web para la gestion interna de Nahan Asesores. Incluye una API en Flask, una base de datos MySQL y un frontend estatico en HTML, CSS y JavaScript.

## Como iniciar el sistema en local

### 1. Entrar al proyecto

```bash
cd /Users/rena/Desktop/nahan-asesores-sistema
```

### 2. Crear y activar el entorno virtual

En macOS o Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

En Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Instalar dependencias de Python:
```bash
pip install -r requirements.txt
```

### 4. Crear la base de datos:

El archivo `database/nahan_asesores.sql` crea la base `nahan_asesores`, sus tablas y datos base como roles, areas y parametros del sistema.

```bash
mysql -u root -p < database/nahan_asesores.sql
```

Importante: este script usa `DROP DATABASE IF EXISTS nahan_asesores`, por lo que elimina y vuelve a crear la base si ya existe.

### 5. Configurar variables de entorno
Crear un archivo `.env` en la raiz del proyecto con los datos de conexion a MySQL:

```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=tu_password
DB_NAME=nahan_asesores
```

### 6. Levantar el backend
Desde la raiz del proyecto, con el entorno virtual activado:

```bash
python -m backend.app
```

Si en tu equipo el comando `python` no existe, usar:

```bash
python3 -m backend.app
```

La API queda disponible en:

```text
http://127.0.0.1:5000
```

Para comprobar que esta funcionando, abrir:

```text
http://127.0.0.1:5000/
```

### 7. Crear el primer usuario
La base de datos inicial no trae usuarios creados. Con el backend funcionando, se puede crear un primer administrador desde la terminal:

```bash
curl -X POST http://127.0.0.1:5000/api/usuarios \
  -H "Content-Type: application/json" \
  -d '{
    "id_rol": 1,
    "id_area": 3,
    "nombres": "Administrador",
    "email": "admin@nahan.cl",
    "password": "CambiarEstaClave123"
  }'
```

Despues de entrar al sistema, cambiar estos datos por credenciales reales.

### 8. Levantar el frontend

En otra terminal, desde la raiz del proyecto:

```bash
python3 -m http.server 5500 --directory frontend
```

Luego abrir el login en el navegador:

```text
http://127.0.0.1:5500/auth/login.html
```

El frontend esta configurado para consumir la API en:

```text
http://127.0.0.1:5000/api
```

## Requisitos previos

Antes de iniciar la aplicacion, se necesita tener instalado:

- Python 3.
- `pip`, el gestor de paquetes de Python.
- MySQL Server.
- Cliente de MySQL para importar el archivo `.sql`; puede ser la terminal de MySQL, MySQL Workbench u otra herramienta equivalente.
- Un navegador web moderno.
- Git, solo si se va a clonar o versionar el proyecto.

## Dependencias principales

Las dependencias del backend estan declaradas en `requirements.txt`. Las principales son:

- Flask: servidor web de la API.
- Flask-CORS: permite que el frontend local consuma la API.
- mysql-connector-python: conexion entre Flask y MySQL.
- python-dotenv: carga variables desde el archivo `.env`.
- bcrypt: hash y validacion de contrasenas.
- PyJWT: soporte para tokens JWT.

## Estructura general del proyecto

```text
backend/
  app.py                 Punto de entrada de la API Flask.
  config/db.py           Conexion a MySQL usando variables de entorno.
  routes/                Rutas de usuarios, auth, tareas, clientes y control de horas.
  utils/security.py      Funciones para hash y validacion de contrasenas.

database/
  nahan_asesores.sql     Script para crear la base de datos y datos base.

frontend/
  auth/                  Login y cierre de sesion.
  dashboard/             Panel principal.
  usuarios/              Gestion de usuarios.
  clientes/              Gestion de clientes.
  tareas/                Gestion de tareas.
  control_horas/         Registro y control de horas.
  assets/                CSS y JavaScript compartido.

requirements.txt         Dependencias Python del backend.
```

## Notas de desarrollo

- El backend corre por defecto en el puerto `5000`.
- El frontend puede servirse en cualquier puerto, pero los archivos JavaScript apuntan actualmente a `http://127.0.0.1:5000/api`.
- Si cambias el puerto del backend, tambien debes actualizar las constantes `API_URL` del frontend.
- No subir credenciales reales al repositorio. El archivo `.env` debe mantenerse local.

## Problemas comunes

- Si aparece un error de conexion a MySQL, revisar que MySQL este iniciado y que `DB_HOST`, `DB_USER`, `DB_PASSWORD` y `DB_NAME` sean correctos.
- Si el frontend muestra que no puede conectar con el servidor, confirmar que Flask este corriendo en `http://127.0.0.1:5000`.
- Si el login falla despues de importar la base, crear primero un usuario porque el script SQL inicial no incluye cuentas.
