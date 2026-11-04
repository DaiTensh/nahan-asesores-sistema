#!/usr/bin/env bash
# Inspección de SOLO LECTURA del servidor de Nahan Asesores (Fase 0 del plan AWS).
#
# No modifica nada: no escribe archivos, no reinicia servicios, no toca la base de datos. No imprime
# valores del .env (solo si cada variable está definida) ni contraseñas. Pensado para ejecutarse por SSH:
#
#     ssh -i LLAVE ubuntu@SERVIDOR 'bash -s' < deploy/scripts/inspeccion_servidor.sh > inspeccion.txt
#
# o, ya dentro del servidor:   bash deploy/scripts/inspeccion_servidor.sh [RUTA_DEL_PROYECTO]
#
# El resultado se puede compartir sin riesgo: revise igualmente que no contenga datos que no quiera enviar.
APP="${1:-/var/www/nahan-asesores-sistema}"
PY="$APP/venv/bin/python"
[ -x "$PY" ] || PY="$APP/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

seccion() { printf '\n=== %s\n' "$1"; }
intentar() { "$@" 2>&1 | head -n "${LIMITE:-12}"; }

echo "Inspección de solo lectura — $(date -u '+%Y-%m-%d %H:%M:%S UTC') — proyecto: $APP"

seccion "Sistema"
uname -sr
(lsb_release -ds 2>/dev/null || grep PRETTY_NAME /etc/os-release 2>/dev/null) | head -1
"$PY" --version 2>&1
intentar mysqld --version
free -m 2>/dev/null | head -2
df -h / 2>/dev/null | tail -1
uptime 2>/dev/null

seccion "Código desplegado"
if [ -d "$APP/.git" ]; then
  git -C "$APP" rev-parse --short HEAD 2>&1
  git -C "$APP" log -1 --format='%h %ad %s' --date=short 2>&1
  git -C "$APP" branch --show-current 2>&1
  echo "cambios locales sin versionar: $(git -C "$APP" status --short 2>/dev/null | wc -l | tr -d ' ')"
else
  echo "(sin repositorio Git en $APP; versión desconocida)"
fi

seccion "Migraciones (solo informa)"
(cd "$APP" 2>/dev/null && LIMITE=20 intentar "$PY" database/migrar.py --comprobar)

seccion "Servicios"
if command -v systemctl >/dev/null 2>&1; then
  for unidad in nginx mysql nahan.service nahan-respaldo.timer nahan-vencimientos.timer; do
    printf '%-28s activo=%-10s habilitado=%s\n' "$unidad" "$(systemctl is-active "$unidad" 2>&1)" "$(systemctl is-enabled "$unidad" 2>&1)"
  done
  systemctl list-timers --all --no-pager 2>/dev/null | grep -i nahan | head -4
else
  echo "(este equipo no tiene systemd: no se inspeccionan los servicios)"
fi

seccion "Configuración (.env): nombres y estado, nunca valores"
if [ -r "$APP/.env" ]; then
  awk -F= '/^[A-Z_][A-Z0-9_]*=/ { v=$0; sub(/^[^=]*=/, "", v); printf "%-40s %s\n", $1, (v==""?"(vacío)":"(definido)") }' "$APP/.env"
  echo "--- valores no secretos"
  grep -E '^(FLASK_ENV|DEBUG|SESSION_COOKIE_SECURE|SESSION_COOKIE_HTTPONLY|SESSION_COOKIE_SAMESITE|TRUST_PROXY|RESPALDO_EXIGIR_DISPOSITIVO_SEPARADO|RESTAURACION_HABILITADA|APP_TIMEZONE|DB_HOST|DB_PORT|DB_CONNECT_TIMEOUT)=' "$APP/.env"
  if grep -q '^SECRET_KEY=dev-secret-key-change-me' "$APP/.env"; then echo "SECRET_KEY: IGUAL A LA CLAVE DE DESARROLLO (inseguro)"; else
    echo "SECRET_KEY: longitud $(grep '^SECRET_KEY=' "$APP/.env" | sed 's/^SECRET_KEY=//' | tr -d '\n' | wc -c | tr -d ' ') caracteres"; fi
else
  echo "(no se puede leer $APP/.env con este usuario)"
fi

seccion "Cuentas de demostración con la contraseña pública (modo informe, sin cambios)"
(cd "$APP" 2>/dev/null && LIMITE=14 intentar "$PY" database/rotar_cuentas_demo.py)

seccion "Respaldos (RF60)"
(cd "$APP" 2>/dev/null && LIMITE=16 intentar "$PY" -m backend.respaldos_programados estado)
DIR_RESPALDO="$(grep -E '^RESPALDO_DIR=' "$APP/.env" 2>/dev/null | sed 's/^RESPALDO_DIR=//')"
if [ -n "$DIR_RESPALDO" ]; then
  df -h "$DIR_RESPALDO" 2>&1 | tail -1
  echo "mismo dispositivo que la aplicación: $([ "$(stat -c %d "$DIR_RESPALDO" 2>/dev/null)" = "$(stat -c %d "$APP" 2>/dev/null)" ] && echo SI || echo no)"
  ls -l "$DIR_RESPALDO" 2>&1 | head -6
fi

seccion "Red y Nginx"
ss -ltn 2>/dev/null | awk 'NR==1 || /:(80|443|8000|3306|22) /' | head -8
(ufw status 2>/dev/null || true) | head -8
printf 'HTTP local: '; curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1/auth/login.html
printf 'HTTPS local: '; curl -sk -o /dev/null -w '%{http_code}\n' --max-time 5 https://127.0.0.1/auth/login.html
printf 'API local: '; curl -s --max-time 5 http://127.0.0.1:8000/ | head -c 120; echo
curl -sI --max-time 5 http://127.0.0.1/auth/login.html 2>/dev/null | grep -iE '^(server|x-frame|x-content|strict-transport|referrer)' | head -5
nginx -t 2>&1 | head -3

seccion "Errores recientes de la aplicación (últimas 24 h)"
LIMITE=15 intentar journalctl -u nahan.service --since '24 hours ago' -p err --no-pager -q
echo; echo "Fin. Nada se modificó."
