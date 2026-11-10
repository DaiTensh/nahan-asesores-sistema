# Procedimiento de actualización y recuperación

Válido para cualquier servidor Linux con la aplicación instalada (rutas de ejemplo; ajústelas a su instalación). **No contiene secretos.** Probado en un entorno aislado con datos ficticios (`scripts/ensayo_despliegue_local.py`, 25 comprobaciones); no se ha ejecutado en un servidor real.

## 1. Identificar versión y esquema
```bash
git -C /var/www/nahan-asesores-sistema rev-parse --short HEAD     # versión desplegada
git -C /var/www/nahan-asesores-sistema status --short             # no debe haber cambios locales sin explicar
cd /var/www/nahan-asesores-sistema && venv/bin/python database/migrar.py --comprobar   # migraciones pendientes (código de salida 1 si faltan)
```
La última migración es la **014** (contraseña temporal con cambio obligatorio; la 013 es la anulación de registros de horas). Un esquema completo tiene 24 tablas, 177 columnas y 36 claves foráneas.

## 2. Respaldo previo comprobable (siempre, antes de actualizar)
1. Respaldo manual desde *Respaldos* (administrador) o `venv/bin/python -m backend.respaldos_programados`.
2. Verificar el paquete («Verificar» en la pantalla o hash SHA-256 en el archivo `.sha256`).
3. **Copiar el paquete `.zip` y su `.sha256` fuera de la carpeta que se va a sustituir y fuera del servidor** (otro equipo o almacenamiento externo). `RESPALDO_DIR` no debe estar dentro del directorio de la aplicación.

## 3. Bloquear el acceso durante la actualización
Detener el servicio (`sudo systemctl stop nahan`) o devolver una página de mantenimiento desde Nginx. Los temporizadores de respaldo y vencimientos pueden seguir.

## 4. Actualizar: primero el esquema, después el código nuevo
```bash
cd /var/www/nahan-asesores-sistema
git fetch origin && git checkout <commit o etiqueta revisada>        # el commit exacto, no «lo último»
venv/bin/pip install -r requirements.txt
venv/bin/python database/migrar.py                                    # aplica 013 y las pendientes (aditivas e idempotentes)
venv/bin/python database/migrar.py --comprobar                        # debe indicar que no hay pendientes
sudo systemctl start nahan && sudo nginx -t && sudo systemctl reload nginx
```
**Las migraciones se aplican antes de que el código nuevo atienda solicitudes**: el código nuevo consulta las columnas de la 013 y, sin ellas, horas e informes responden 500.

## 5. Comprobar
`systemctl status nahan`, `journalctl -u nahan -n 100`; abrir el login por HTTPS; iniciar sesión; *Control de horas* (listado y totales), un informe de horas y de cobro; y `SELECT COUNT(*) FROM registro_tiempo WHERE estado_registro <> 'VIGENTE'` coherente con lo esperado.

## 6. Recuperación — restricciones que ya existen datos de anulación
| Acción | Resultado | ¿Seguro? |
|---|---|---|
| Volver al **código anterior** (sin tocar el esquema) | Arranca y responde, pero **vuelve a contar los registros anulados** (totales, informes y cobros inflados) | **No es una recuperación funcional segura** si hay anulaciones. Solo aceptable con 0 anulaciones |
| **Revertir la migración 013** (quitar las 4 columnas) | **Elimina estado, responsable, fecha y motivo de las anulaciones**; los anulados vuelven a sumar | **No usar sobre datos reales** sin preservar esa información; además el código nuevo deja de funcionar |
| **Restaurar un respaldo** | Reemplaza los datos por los del respaldo; lo posterior se pierde (la «copia previa» automática lo conserva) | Es la vía de recuperación; seguir el apartado 7 |
| Volver al código anterior a la **014** (sin tocar el esquema) | El código anterior ignora `debe_cambiar_password` y `version_credenciales`: **deja de exigirse el cambio de las contraseñas temporales** (quien tenga una pendiente opera con ella) y las sesiones ya no se invalidan al cambiar credenciales | No es seguro mientras existan cuentas con contraseña temporal pendiente: cámbielas o restablézcalas antes, o no retroceda |
| **Revertir la migración 014** (quitar las 2 columnas) | Se pierde qué cuentas tenían el cambio pendiente; el código nuevo deja de funcionar en inicio de sesión | No usar sobre datos reales; exige revertir también el código |
La vía recomendada ante un problema es **corregir hacia adelante** (nuevo commit y volver a desplegar) o **restaurar un respaldo**, no retroceder el código.

## 7. Restaurar un respaldo (en particular uno anterior a la migración 013)
1. **Mantener el sistema fuera de uso durante toda la operación** (servicio detenido o mantenimiento en Nginx). Al terminar la restauración la API vuelve a aceptar solicitudes con el esquema del respaldo: si es anterior a 013, horas, informes y registro manual responden 500 hasta migrar.
2. Habilitar `RESTAURACION_HABILITADA=true` solo mientras dure la operación, restaurar desde *Respaldos* (exige confirmación y contraseña) y volver a `false`. La respuesta avisa «el respaldo es de un esquema anterior … faltan: 013». **La restauración no ejecuta migraciones.**
3. `venv/bin/python database/migrar.py` y `venv/bin/python database/migrar.py --comprobar`.
4. Comprobar *Control de horas*, un informe de horas y de cobro, y los registros no vigentes (las horas restauradas quedan VIGENTES; las anulaciones posteriores al respaldo se perdieron).
5. **Solo entonces** volver a habilitar el acceso.
Si la operación falla a medias, la restauración revierte al estado anterior y deja la «copia previa» indicada en el detalle.

## 8. Contraseñas temporales (desde la 014)
- El administrador crea cuentas y restablece contraseñas desde *Usuarios*; el sistema genera una contraseña temporal aleatoria que se muestra **una sola vez** (no se guarda en claro, no se envía por correo, no queda en auditoría ni en logs). La persona debe elegir una propia en su primer acceso; mientras tanto el servidor bloquea el resto de la API.
- Restablecer invalida la contraseña y las sesiones anteriores de esa persona. No se puede restablecer la propia cuenta con esta acción (use *Cambiar contraseña* del menú de usuario).
- Tras **restaurar un respaldo anterior a la 014** ejecute `database/migrar.py` antes de habilitar el acceso: sin las columnas nuevas el inicio de sesión responde 500.

## 9. Qué NO hacer
- No probar restauraciones ni simulaciones (horas ficticias, anulaciones, fallos) sobre la base real.
- No dejar `TEMPORIZADOR_AVISO_HORAS`, `CSRF_COMPROBAR_ORIGEN` ni ningún valor de prueba distinto del de producción.
