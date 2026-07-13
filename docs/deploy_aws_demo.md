# Despliegue Demo AWS EC2 - Nahan Asesores

Esta guia prepara una demo en una instancia EC2 Ubuntu con MySQL local, Gunicorn y Nginx. No usa RDS, S3, Docker, GitHub Actions, dominio ni HTTPS en esta etapa.

## 1. Prerrequisitos

- Cuenta AWS con permisos para EC2 y Security Groups.
- Llave SSH para acceder a la instancia.
- Repositorio disponible para clonar.
- Archivo `.env` creado desde `.env.example`, sin subir secretos al repositorio.

## 2. Configuracion AWS

Crear una instancia EC2 Ubuntu LTS con:

- Tipo sugerido demo: `t3.micro` o superior.
- Disco: 16 GB o superior.
- Security Group:
  - SSH `22` solo desde IP administrativa.
  - HTTP `80` abierto para demo.
  - No exponer `3306`.
  - No exponer `8000`.

## 3. Instalacion Ubuntu

```bash
sudo apt update
sudo apt upgrade -y
sudo timedatectl set-timezone America/Santiago
timedatectl
```

## 4. Git, Python y venv

```bash
sudo apt install -y git python3 python3-venv python3-pip build-essential
sudo mkdir -p /var/www
sudo chown ubuntu:www-data /var/www
cd /var/www
git clone <URL_DEL_REPOSITORIO> nahan-asesores
cd /var/www/nahan-asesores
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 5. MySQL local

```bash
sudo apt install -y mysql-server
sudo systemctl enable mysql
sudo systemctl start mysql
sudo mysql
```

Dentro de MySQL, usar valores propios:

```sql
CREATE DATABASE nahan_asesores CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'nahan_app'@'localhost' IDENTIFIED BY 'CAMBIAR_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON nahan_asesores.* TO 'nahan_app'@'localhost';
FLUSH PRIVILEGES;
SET GLOBAL time_zone = 'America/Santiago';
```

Si MySQL no tiene tablas de zona horaria cargadas, configurar temporalmente offset local o cargar zonas del sistema:

```bash
mysql_tzinfo_to_sql /usr/share/zoneinfo | sudo mysql mysql
sudo systemctl restart mysql
```

Importar el script SQL:

```bash
mysql -u root -p < database/nahan_asesores.sql
```

Luego confirmar que la base y tablas existen. No usar `root` desde Flask.

## 6. Variables de entorno

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

Variables esperadas:

```env
FLASK_ENV=production
DEBUG=false
SECRET_KEY=
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=nahan_app
DB_PASSWORD=
DB_NAME=nahan_asesores
SESSION_COOKIE_SECURE=false
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Lax
PERMANENT_SESSION_LIFETIME=480
ALLOWED_ORIGINS=
TRUST_PROXY=true
APP_TIMEZONE=America/Santiago
```

`SESSION_COOKIE_SECURE=false` es temporal mientras no exista HTTPS. Al agregar HTTPS, cambiar a `true`.

## 7. Pruebas

```bash
source venv/bin/activate
venv/bin/python -m pytest
```

Validar import de Flask:

```bash
venv/bin/python -c "from backend.app import app; print(app.name)"
```

## 8. Gunicorn

Comando final:

```bash
venv/bin/gunicorn --workers 2 --bind 127.0.0.1:8000 backend.app:app
```

Gunicorn debe escuchar solo en `127.0.0.1`; Nginx sera el punto publico.

## 9. systemd

Copiar plantilla:

```bash
sudo cp deploy/systemd/nahan.service /etc/systemd/system/nahan.service
sudo systemctl daemon-reload
sudo systemctl enable nahan
sudo systemctl start nahan
sudo systemctl status nahan
```

Logs:

```bash
journalctl -u nahan -f
```

## 10. Nginx

```bash
sudo apt install -y nginx
sudo cp deploy/nginx/nahan.conf /etc/nginx/sites-available/nahan
sudo ln -s /etc/nginx/sites-available/nahan /etc/nginx/sites-enabled/nahan
sudo nginx -t
sudo systemctl reload nginx
```

La configuracion:

- Sirve `frontend/` como archivos estaticos.
- Redirige `/api/` a Gunicorn en `127.0.0.1:8000`.
- Mantiene frontend y API bajo el mismo origen.

## 11. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx HTTP'
sudo ufw enable
sudo ufw status
```

## 12. Verificacion

Abrir:

```text
http://IP_PUBLICA_EC2/auth/login.html
```

Probar:

- Login.
- Dashboard.
- Clientes.
- Tareas.
- Control de horas.
- Administracion para admin.
- Logout.

## 13. Logs y reinicio

```bash
sudo systemctl restart nahan
sudo systemctl restart nginx
journalctl -u nahan -n 100 --no-pager
sudo tail -f /var/log/nginx/error.log
```

## 14. Actualizacion futura mediante Git

```bash
cd /var/www/nahan-asesores
git pull
source venv/bin/activate
pip install -r requirements.txt
venv/bin/python -m pytest
sudo systemctl restart nahan
sudo systemctl reload nginx
```

## 15. Rollback

```bash
cd /var/www/nahan-asesores
git log --oneline
git checkout <COMMIT_ANTERIOR>
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart nahan
```

Si hubo cambios SQL futuros, restaurar respaldo antes de reiniciar.

## 16. Respaldo manual inicial MySQL

```bash
mysqldump -u root -p nahan_asesores > ~/nahan_asesores_backup_$(date +%Y%m%d_%H%M).sql
```

## 17. Eliminacion de recursos AWS

Cuando termine la demo:

- Descargar respaldos necesarios.
- Detener o terminar instancia EC2.
- Eliminar volumen EBS si no se conserva.
- Revisar Security Groups no usados.
- Eliminar llave si fue exclusiva para esta demo.

## 18. Zona horaria

Estrategia de esta version:

- Ubuntu: `America/Santiago`.
- Flask: `APP_TIMEZONE=America/Santiago`.
- MySQL: `time_zone = America/Santiago` o zona del sistema configurada en Chile.
- Frontend: solo muestra fechas recibidas y calcula contador visual desde hora de inicio del backend.

No se migran datos ni se cambia el esquema en esta etapa.
