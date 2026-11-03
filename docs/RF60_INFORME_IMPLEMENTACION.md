# Informe de implementación RF60

## A. Resumen

RF60 respalda históricamente la información: un paquete `.zip` con el volcado de MySQL, los adjuntos de tareas y un manifiesto con huellas SHA-256. Se ejecuta a diario con un temporizador de systemd y a pedido del administrador desde **Administración › Respaldos**; cada ejecución queda en la tabla `respaldo` con fecha, hora, tipo y estado, y el administrador puede verificar y restaurar un respaldo. No se usan dependencias ni servicios nuevos (`mysqldump`, `zipfile`, `mysql-connector`, systemd, ya presentes).

| CA | Estado | Cómo se cumple |
|---|---|---|
| CA1 programado y automático | Implementado; **instalación en el servidor pendiente** | `deploy/systemd/nahan-respaldo.service` y `.timer` (diario 02:00, `Persistent=true`) ejecutan `python -m backend.respaldos_programados`. Un proceso por vez; sin planificador dentro de Gunicorn. |
| CA2 respaldo manual | Implementado | `POST /api/respaldos` (solo administrador, validado en el backend) y botón en la pantalla. |
| CA3 fecha, hora y estado | Implementado | Tabla `respaldo` (migración 010) y panel «Historial». También los intentos fallidos. |
| CA4 restaurar | Implementado, **deshabilitado por defecto** | `POST /api/respaldos/<id>/restaurar` y CLI. Se activa con `RESTAURACION_HABILITADA=true`. |
| CA5 ubicación segura y separada | Implementado y verificable; **pendiente de validación ambiental** | `RESPALDO_DIR` fuera del proyecto, permisos 0700/0600, sin descarga por HTTP, comprobación de dispositivo. Falta un destino independiente real (ver §F). |

## B. Qué contiene un respaldo

```
nahan-respaldo-AAAAMMDDTHHMMSSZ-xxxxxxxx.zip
├── manifest.json        formato, migraciones aplicadas, tablas y filas, huellas SHA-256
├── base_de_datos.sql    mysqldump (una fila por INSERT; sin la tabla `respaldo`)
└── adjuntos/...         archivos de ADJUNTOS_DIR (RF54), sin enlaces simbólicos ni nombres inseguros
nahan-respaldo-….zip.sha256   huella del paquete (referencia que no depende de la base de datos)
```

Tampoco se incluye `intento_login_fallido` (SEC-02): es estado operativo y restaurar no debe «perdonar» intentos recientes.

Respaldar solo MySQL no alcanza: los adjuntos viven en disco y `documento.url_archivo` solo guarda su nombre. La tabla `respaldo` se excluye a propósito para que el historial sobreviva a una restauración.

## C. Archivos

- `backend/utils/respaldos.py`: servicio (configuración, almacenamiento, bloqueo, mysqldump, paquete, validación, historial, respaldo, restauración).
- `backend/routes/respaldos_routes.py`: API de administración. Registrada en `backend/app.py`, junto con un `before_request` que responde 503 al resto de `/api/` mientras una restauración reemplaza los datos.
- `backend/respaldos_programados.py`: punto de entrada del temporizador y de la operación por consola.
- `database/migraciones/010_respaldos.sql`, `database/nahan_asesores.sql`, `database/migrar.py` (marcador `010`).
- `backend/utils/auditoria.py`: `respaldo → Respaldos` (los eventos aparecen en RF49 y RF56 sin más cambios).
- `frontend/respaldos/` y entrada «Respaldos» en el menú de administración.
- `deploy/systemd/nahan-respaldo.*`; `nahan.service` sube el `--timeout` de Gunicorn a 300 s (respaldo y restauración manuales son síncronos).
- `.env.example`, `tests/test_rf60_*.py`, `tests/mysql_desechable.py`.

## D. Configuración (`.env`)

| Variable | Defecto | Uso |
|---|---|---|
| `RESPALDO_DIR` | vacío (los respaldos se rechazan) | Carpeta absoluta de los paquetes, fuera del proyecto. |
| `RESPALDO_RETENCION_MAXIMA` | 30 (mín. 3) | Paquetes que se conservan; el historial se conserva siempre. |
| `RESPALDO_EXIGIR_DISPOSITIVO_SEPARADO` | false | Con true, falla si `RESPALDO_DIR` está en el mismo dispositivo que la aplicación. |
| `RESPALDO_DB_USER` / `_PASSWORD` | `DB_USER` / `DB_PASSWORD` | Cuenta del respaldo (basta `SELECT`). |
| `RESTAURACION_HABILITADA` | false | Habilita restaurar. |
| `RESTAURACION_DB_NAME` | `DB_NAME` | Base de destino; otra base permite ensayar sin tocar la activa. |
| `RESTAURACION_DB_USER` / `_PASSWORD` | cuenta del respaldo | Necesita `CREATE`, `DROP` e `INSERT` sobre la base de destino. |
| `RESPALDO_TIMEOUT_SEGUNDOS`, `RESPALDO_MAX_MB`, `MYSQLDUMP_BIN` | 600, 4096, `mysqldump` | Límites y binario. |

El destino de la restauración lo fija el servidor, nunca la solicitud.

## E. Operación

- **Manual**: Administración › Respaldos › «Ejecutar respaldo ahora». Verificar comprueba integridad sin restaurar.
- **Programado** (se puede probar en cualquier equipo con `RESPALDO_DIR`): `python -m backend.respaldos_programados` (códigos de salida 0 / 1 / 75 si había otra operación en curso). Instalación en el servidor, **no ejecutada**:
  ```bash
  sudo cp deploy/systemd/nahan-respaldo.* /etc/systemd/system/
  sudo systemctl daemon-reload && sudo systemctl enable --now nahan-respaldo.timer
  systemctl list-timers nahan-respaldo.timer     # próxima ejecución
  ```
- **Restaurar desde la aplicación**: botón «Restaurar» (si está habilitada). Exige escribir `RESTAURAR` y la contraseña del administrador. Pasos: validar el paquete completo → tomar una copia `PREVIO_RESTAURACION` de la base activa → cargar el volcado → comprobar el conteo de filas de cada tabla → copiar adjuntos (nunca se borra ninguno). Si algo falla después de tocar la base, se vuelve automáticamente a la copia previa; si eso también falla, el mensaje indica el paquete para restaurar a mano.
- **Recuperación total** (la base se perdió y no hay historial): con la base vacía creada,
  ```bash
  RESTAURACION_HABILITADA=true python -m backend.respaldos_programados restaurar \
      --archivo nahan-respaldo-….zip --confirmo-base nahan_asesores
  python database/migrar.py        # recrea la tabla `respaldo` (migración 010)
  ```
  El paquete se verifica con su `.sha256`; nombre y base de destino deben repetirse.
- **Qué se pierde al restaurar un respaldo antiguo**: lo escrito después del respaldo en las tablas del negocio y en `auditoria`. Eso queda en el paquete `PREVIO_RESTAURACION` (con su propia verificación) y el historial de respaldos/restauraciones se conserva íntegro.

## F. Almacenamiento seguro y separado (CA5)

Implementado: carpeta fuera del proyecto, de `frontend/` y de los adjuntos (se rechaza si está dentro o los contiene); solo se crea el último nivel de la ruta (un volumen sin montar no se rellena en el disco raíz); permisos 0700 en la carpeta y 0600 en paquetes y huellas; dueño verificado; prueba de escritura; espacio libre; **sin ninguna ruta HTTP de descarga** (los paquetes contienen toda la información). La pantalla y `python -m backend.respaldos_programados estado` muestran cada comprobación.

Una carpeta distinta en el mismo disco **no** cumple CA5. Cómo comprobar la independencia (el sistema compara dispositivos, que es lo máximo que se puede afirmar desde el sistema operativo):

```bash
df -P /var/www/nahan-asesores-sistema /mnt/nahan-respaldos   # «Filesystem» distinto
findmnt -T /mnt/nahan-respaldos                               # punto de montaje propio
stat -c '%d' /var/www/nahan-asesores-sistema /mnt/nahan-respaldos   # números de dispositivo distintos
```
y, en AWS, que el volumen de destino sea distinto del volumen raíz (o que el destino sea otra máquina/servicio). Alternativas evaluadas:

| Alternativa | Independencia | Requiere | Estado |
|---|---|---|---|
| Volumen EBS adicional montado en `RESPALDO_DIR` | Otro volumen (misma instancia y zona) | Crear y adjuntar volumen en AWS | Compatible; **requiere autorización** |
| Copia posterior a S3 privado (fuera de la aplicación) | Otro servicio | Bucket, rol IAM y AWS CLI | Compatible; **requiere autorización** |
| Montaje de un destino remoto (NFS, mountpoint-s3, etc.) | Otra máquina o servicio | Infraestructura | Compatible |
| Otra carpeta del mismo disco | Ninguna | Nada | Funciona con un aviso explícito; no cumple CA5 |

## G. Seguridad

Autenticación y rol de administrador en cada ruta; restauración con confirmación escrita y contraseña (cinco rechazos en 15 minutos la bloquean con 429 y quedan en `auditoria` como `RESTAURACION_RECHAZADA`); validación de parámetros (límite cerrado `10/20/50/100`, id entero); sin shell y con la contraseña de MySQL solo en un archivo temporal 0600 que se borra (nunca en argumentos ni en registros); nombres de paquete generados por el sistema y validados con expresión anclada; paquete validado contra la huella registrada y contra el manifiesto, sin rutas absolutas ni `..`, enlaces simbólicos, cifrado, duplicados ni miembros sin declarar; el volcado solo admite `DROP/CREATE TABLE` e `INSERT` (se reproduce con mysql-connector, sin el cliente `mysql`, para que `\!` o `source` no existan); un único respaldo/restauración por vez entre todos los procesos (bloqueo de archivo) y las operaciones huérfanas se cierran como fallidas; auditoría con `registrar_auditoria()` (`RESPALDO_MANUAL`, `RESPALDO_MANUAL_FALLIDO`, `RESTAURACION_RESPALDO`, `RESTAURACION_FALLIDA`).

## H. Limitaciones conocidas

- Los respaldos programados no escriben en `auditoria` (`auditoria.id_usuario` es obligatorio y no hay usuario); su constancia es la tabla `respaldo`.
- Respaldo y restauración manuales son síncronos; con el volumen de datos actual (≈ 1 MB) duran segundos. Con datos mucho mayores convendría ejecutarlos en segundo plano.
- El respaldo no se cifra: la protección es la carpeta 0700. Si el destino sale de la máquina, cifrar en el destino.
- Los triggers y rutinas no están soportados (el esquema no tiene): si se agregan, el respaldo falla con un mensaje explícito en lugar de producir un paquete irrecuperable.
- Un respaldo de un esquema anterior se restaura con aviso (hay que ejecutar `database/migrar.py`); uno de una versión más nueva se rechaza.
- Migraciones: `008` (seguridad, SEC-02) y `010` son independientes; en la rama de cierre del Incremento 4 conviven las dos.

## I. Pruebas

`tests/test_rf60_respaldos.py` (servicio, sin MySQL), `tests/test_rf60_api.py` (API, interfaz y despliegue) y `tests/test_rf60_mysql_real.py` (servidor MySQL desechable local, puerto efímero y datos ficticios: respaldo con una cuenta sin `DROP`, restauración con igualdad de las 22 tablas, falla a medias con recuperación automática, paquetes manipulados, concurrencia, modo mantenimiento, migración 010, compatibilidad con RF47 y RF49). Las pruebas de MySQL real se omiten si no hay `mysqld`/`mysqldump` o con `NAHAN_TEST_SIN_MYSQL=1`. Ninguna toca una base real.

```bash
DB_HOST=127.0.0.1 DB_PORT=1 DB_USER=aislado DB_PASSWORD=aislado DB_NAME=aislado SMTP_HOST= SMTP_USER= SMTP_PASSWORD= \
  python -m pytest tests -q -p no:cacheprovider
```
