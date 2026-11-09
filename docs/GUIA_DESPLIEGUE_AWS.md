# Guía de operación y despliegue en AWS — Nahan Asesores

Esta guía describe el despliegue que **definen los archivos versionados**. No
se consultó ni modificó una cuenta AWS durante su elaboración. Los valores
reales de instancia, región, direcciones, llaves, grupo de seguridad, DNS,
certificado, volúmenes y estado de servicios deben confirmarse en AWS y en la
instancia antes de operar.

## 1. Configuración comprobada en el repositorio

Los siguientes valores provienen de `deploy/` y de
`docs/deploy_aws_demo.md`; no certifican el estado actual de AWS:

| Componente | Configuración versionada |
|---|---|
| Sistema esperado | Ubuntu, EC2 |
| Aplicación | Flask servido por Gunicorn |
| Unidad systemd | `nahan.service`; ejecuta como `ubuntu:www-data` |
| Directorio de trabajo | `/var/www/nahan-asesores-sistema` |
| Entorno virtual esperado | `/var/www/nahan-asesores-sistema/venv` |
| Backend | Gunicorn en `127.0.0.1:8000`, blueprint Flask en `backend.app:app` |
| Frontend y proxy | Nginx sirve `frontend/` y reenvía `/api/` a Gunicorn |
| Base de datos | MySQL local; la unidad espera `mysql.service` |
| HTTP | Plantilla `deploy/nginx/nahan.conf` escucha en puerto 80 |
| Tareas programadas | Timers opcionales de respaldo (02:00) y aviso de vencimientos (07:00), según sus unidades versionadas |

No hay evidencia en este repositorio que confirme una IP, nombre de DNS,
región, identificador/tamaño de instancia, volumen montado, llaves activas,
reglas de Security Group, HTTPS activo o estado de los servicios. La plantilla
HTTPS es un ejemplo aparte; no asumas que está instalada.

## 2. Iniciar la instancia y conectarse

1. En la consola AWS, selecciona la cuenta, región e instancia correctas y
   confirma su estado, identificador, sistema, llave asociada y direcciones.
2. Inicia la instancia desde **EC2 → Instances → Instance state → Start
   instance**. Espera a que los chequeos de estado estén aprobados y confirma
   la IP pública vigente; una IP pública puede cambiar al detener e iniciar
   una instancia si no hay Elastic IP.
3. Antes de SSH, confirma que el Security Group limita el puerto 22 a la IP
   administrativa. Para la demo HTTP, el puerto 80 puede estar abierto según
   la política acordada. No expongas los puertos 3306 (MySQL) ni 8000
   (Gunicorn) a Internet.

En macOS/Linux, con la llave descargada fuera del repositorio:

```bash
chmod 400 <ruta-a-la-llave.pem>
ssh -i <ruta-a-la-llave.pem> ubuntu@<ip-publica-confirmada>
```

En Windows, usa OpenSSH/PowerShell con el usuario, ruta e IP confirmados:

```powershell
ssh -i <ruta-a-la-llave.pem> ubuntu@<ip-publica-confirmada>
```

`ubuntu` es el usuario que figura en la unidad systemd versionada. Si la
instancia tiene otra AMI/imagen o usuario, confirma el usuario correcto en AWS
antes de conectarte; no pruebes credenciales de forma repetida.

## 3. Verificar los servicios y la aplicación

Dentro de la instancia:

```bash
sudo systemctl status nahan.service nginx mysql --no-pager
sudo systemctl list-timers --all --no-pager | grep -E 'nahan-(respaldo|vencimientos)'
```

El segundo comando puede no mostrar unidades si los timers no se instalaron o
habilitaron. Verifica backend y frontend localmente:

```bash
curl -fsS http://127.0.0.1:8000/
curl -I http://127.0.0.1/auth/login.html
sudo nginx -t
```

La primera petición debe responder con el mensaje de identificación de la
API; la segunda comprueba la página servida por Nginx. Comprueba MySQL sin
mostrar secretos:

```bash
sudo systemctl is-active mysql
mysql -h 127.0.0.1 -u <usuario-de-aplicacion> -p <nombre-de-base> -e 'SELECT 1;'
```

Usa los nombres de base y usuario confirmados para esa instancia y escribe la
contraseña solo en el prompt. No uses `cat .env`, no copies sus valores en
terminales compartidas y no habilites el puerto 3306 público.

## 4. Actualizar el código y las dependencias

Este procedimiento es una referencia operativa, no se ejecutó en AWS. Antes
de actualizar:

1. Confirma la instancia y la rama aprobada para ese entorno.
2. Revisa estado, rama y commit; detente si hay cambios locales. No uses
   `reset`, `clean`, `checkout` para descartar trabajo ni sobrescribas
   archivos locales.
3. Confirma respaldo reciente y ventana de mantenimiento. Si habrá migración,
   revisa su SQL, compatibilidad y plan de recuperación con el responsable de
   la base.

Con el repositorio y rama aprobados:

```bash
cd /var/www/nahan-asesores-sistema
git status --short
git branch --show-current
git rev-parse --short HEAD
git fetch origin
git pull --ff-only origin <rama-aprobada>
./venv/bin/pip install -r requirements.txt
./venv/bin/python database/migrar.py --comprobar
```

`git pull --ff-only` evita crear un merge local. No continúes si hay cambios
locales, la rama no coincide, hay conflictos o la comprobación detecta una
migración sin revisar. Las migraciones modifican la base de datos: solo deben
aplicarse bajo un plan aprobado y con respaldo verificado. **No ejecutes**
`database/nahan_asesores.sql` directamente sobre una base con datos: el archivo
comienza con `DROP DATABASE`. Tampoco ejecutes el instalador de desarrollo ni
la siembra de usuarios demo en producción.

Tras la actualización aprobada:

```bash
sudo systemctl restart nahan.service
sudo systemctl status nahan.service --no-pager
curl -fsS http://127.0.0.1:8000/
curl -I http://127.0.0.1/auth/login.html
```

Recarga Nginx solamente si cambió su configuración:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

`git pull` no actualiza la copia activa de la plantilla en
`/etc/nginx/sites-available/nahan`; tras un cambio, copia explícitamente la
plantilla revisada, ejecuta `nginx -t` y luego recarga.

## 5. Comprobar Nginx y el backend

```bash
sudo nginx -t
sudo systemctl is-active nginx
sudo systemctl is-active nahan.service
curl -fsS http://127.0.0.1:8000/
curl -I http://127.0.0.1/auth/login.html
sudo ss -ltn
```

Confirma que Gunicorn escucha solo en `127.0.0.1:8000`, y que MySQL no queda
expuesto externamente. La configuración de Nginx registra límites diferentes
para solicitudes generales y adjuntos; contrástalos con `.env` y con los
parámetros de MySQL antes de cambiar límites.

## 6. Revisar logs

```bash
sudo journalctl -u nahan.service -n 100 --no-pager
sudo journalctl -u nahan.service --since '1 hour ago' --no-pager
sudo tail -n 100 /var/log/nginx/error.log
sudo tail -n 100 /var/log/nginx/access.log
sudo journalctl -u mysql -n 100 --no-pager
```

Los logs pueden contener datos operativos; revisa y redacta información
personal antes de compartirlos.

## 7. Respaldos y recuperación

La configuración incluye un respaldo RF60 de base de datos y adjuntos, con
un timer diario a las 02:00, pero su instalación, habilitación y ejecución
reales requieren confirmación. Verifica `nahan-respaldo.timer`,
`nahan-respaldo.service`, la última ejecución y el destino definido por
`RESPALDO_DIR`. En producción, el ejemplo de entorno recomienda un directorio
en un dispositivo separado y `RESPALDO_EXIGIR_DISPOSITIVO_SEPARADO=true`;
confirma que el volumen esté montado y que el respaldo sea legible por el
servicio. No publiques los paquetes de respaldo.

Como respaldo manual **solo de MySQL** (no incluye adjuntos), el patrón
interactivo es:

```bash
mysqldump -h 127.0.0.1 -u <usuario-de-respaldo> -p \
  --single-transaction <nombre-de-base> > <ruta-segura>/nahan-asesores-<fecha>.sql
```

El cliente solicita la contraseña en el prompt. Guarda el archivo en un
volumen protegido fuera del directorio del repositorio, restringe su acceso y
verifica que el comando termine correctamente y el archivo tenga contenido.
Usa el respaldo RF60 configurado para incluir adjuntos. No consideres una
copia de la base como respaldo completo del sistema.

Para diagnosticar una interrupción, revisa primero estado/logs de MySQL,
Gunicorn y Nginx; confirma espacio en disco, montaje de respaldos y
conectividad local. Reinicia únicamente el servicio afectado después de
entender la causa. Si hay corrupción o pérdida de datos, no restaures ni
ejecutes migraciones a ciegas: detén escrituras, preserva el estado actual,
verifica el respaldo y sigue el procedimiento de recuperación RF60 aprobado.
La restauración reemplaza datos y exige una decisión del responsable. El
procedimiento RF60 versionado valida el paquete, crea una copia
`PREVIO_RESTAURACION` y tiene recuperación automática ante fallos; consulta
[el informe RF60](./RF60_INFORME_IMPLEMENTACION.md) antes de usarlo. La
restauración está deshabilitada por defecto (`RESTAURACION_HABILITADA=false`)
y su activación requiere autorización explícita.

## 8. Reiniciar o detener

Reinicio controlado de la aplicación:

```bash
sudo systemctl restart nahan.service
sudo systemctl status nahan.service --no-pager
```

Para detener solo la aplicación:

```bash
sudo systemctl stop nahan.service
```

Si una versión de aplicación deja de responder y MySQL está sano, sigue el
proceso de actualización aprobado hacia el commit anterior, solo con el
directorio de trabajo limpio y compatibilidad de esquema confirmada:

```bash
cd /var/www/nahan-asesores-sistema
git status --short
git rev-parse --short HEAD
git switch --detach <commit-aprobado>
./venv/bin/pip install -r requirements.txt
sudo systemctl restart nahan.service
sudo systemctl status nahan.service --no-pager
```

Este procedimiento revierte código, no datos ni migraciones. No reviertas
código si el esquema nuevo no es compatible; solicita un plan de recuperación
antes de restaurar una base.

Para detener la instancia EC2, usa **EC2 → Instance state → Stop instance** y
confirma el impacto. Detener la instancia no necesariamente detiene cargos por
volúmenes EBS, direcciones Elastic IP u otros recursos asociados. No elijas
**Terminate** como sustituto de Stop: terminar puede eliminar la instancia y
sus datos según la configuración.

## 9. Seguridad y costos

- Mantén SSH limitado a las IP administrativas; no abras MySQL ni Gunicorn al
  público.
- La plantilla principal sirve HTTP en puerto 80; no hay evidencia de HTTPS
  activo. No habilites `SESSION_COOKIE_SECURE=true` hasta que HTTPS esté
  desplegado y probado. La plantilla HTTPS es un ejemplo, no una confirmación
  de instalación.
- Protege `.env`, la llave SSH, paquetes de respaldo y logs. No los incluyas
  en Git ni en capturas o mensajes.
- Confirma periódicamente los permisos, grupos de seguridad, parches del
  sistema, cuotas de disco y almacenamiento separado de respaldos.
- Revisa en AWS el costo de EC2, EBS, snapshots, IP pública/Elastic IP,
  transferencia de datos y recursos detenidos. La tarifa y tipo de instancia
  dependen de la región y la cuenta; este repositorio no los verifica.
- El tipo `t3.micro`, tamaño de disco y reglas sugeridos en la guía de demo
  anterior son recomendaciones, no el inventario real ni un compromiso de
  disponibilidad.

## 10. Pendiente de confirmación en AWS

Antes de operar, confirma en AWS: cuenta y región; ID/AMI/estado de instancia;
IP pública o DNS; llave y usuario SSH; Security Group; discos y punto de
montaje de respaldos; valores operativos de `.env` (sin compartirlos);
unidades systemd realmente instaladas y habilitadas; configuración activa de
Nginx; certificado/DNS/HTTPS; versión desplegada y rama autorizada; última
prueba de respaldo/restauración; y responsable de aprobar cambios o
restauraciones.

Este trabajo documentó y revisó plantillas del repositorio solamente. No se
inició, detuvo, inspeccionó ni modificó una instancia, servicio o base de datos
de AWS.
