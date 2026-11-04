# HTTPS para el servidor de Nahan Asesores (RNF04)

Estado actual: el servidor se sirve **solo por HTTP** (`deploy/nginx/nahan.conf`). Con HTTP, la contraseña y la cookie de
sesión viajan sin cifrar; no debe usarse con datos ni credenciales reales. Este documento deja lista la activación; **nada de
esto se ha ejecutado** y requiere autorización (cambia reglas de red y puede tener un costo pequeño).

## Qué se necesita (las tres cosas)

| Requisito | Opciones | Costo aproximado |
|---|---|---|
| Un nombre de dominio que apunte a la IP pública del servidor | Dominio propio (≈ 10 USD/año) o un subdominio gratuito de un servicio de DNS dinámico | 0–10 USD/año |
| Puerto 443 abierto en el grupo de seguridad de la instancia | Regla de entrada TCP 443 (y mantener la 80 para el desafío de certbot) | 0 |
| Un certificado válido | Let's Encrypt con `certbot` (gratuito, se renueva solo cada 60–90 días) | 0 |

Sin dominio no hay certificado de confianza. Un certificado autofirmado cifra el tráfico pero el navegador muestra una
advertencia: sirve para una prueba interna, **no** para presentar el sistema al cliente.

## Orden de activación (no alterarlo)

1. **Antes de exponer el servidor:** rotar o desactivar las cuentas de demostración
   (`python database/rotar_cuentas_demo.py`; ver `docs/deploy_aws_demo.md`). Nunca encender el servidor con la contraseña pública.
2. Instantánea del volumen (para poder volver atrás).
3. Apuntar el dominio a la IP y abrir el puerto 443 en el grupo de seguridad.
4. Instalar certbot y emitir el certificado:
   ```bash
   sudo apt install certbot
   sudo mkdir -p /var/www/certbot
   sudo certbot certonly --webroot -w /var/www/certbot -d DOMINIO
   ```
5. Copiar `deploy/nginx/nahan-https.conf.example` a `/etc/nginx/sites-available/nahan`, reemplazar `DOMINIO`, y:
   ```bash
   sudo nginx -t && sudo systemctl reload nginx
   ```
6. Comprobar `https://DOMINIO/auth/login.html` y que `http://DOMINIO/` redirige (301) a HTTPS.
7. **Recién entonces** poner `SESSION_COOKIE_SECURE=true` en el `.env` del servidor y reiniciar `nahan.service`. Con `true` sobre
   HTTP nadie puede iniciar sesión (el navegador descarta la cookie).
8. Comprobar la renovación: `sudo certbot renew --dry-run`.
9. Dejar HSTS en 300 s unos días; si no hay problemas, subirlo a 31536000 en la plantilla y recargar Nginx.

## Comprobaciones después de activar

```bash
curl -sI http://DOMINIO/            # 301 hacia https
curl -sI https://DOMINIO/auth/login.html | grep -iE "strict-transport|x-frame|nosniff"
curl -s -o /dev/null -w "%{http_code}\n" https://DOMINIO/api/auth/me   # 401 sin sesión
```

En el navegador: iniciar sesión, abrir el dashboard y comprobar que la cookie `session` figura como `Secure` y `HttpOnly`.

## Reversión

Volver a copiar `deploy/nginx/nahan.conf`, `sudo nginx -t && sudo systemctl reload nginx`, y poner
`SESSION_COOKIE_SECURE=false` **antes** de reiniciar la aplicación (si no, nadie podrá iniciar sesión por HTTP).

## Lo que esta plantilla también añade

- `limit_req` de 10 solicitudes por minuto y por IP en `/api/login` (ráfaga de 5), además del límite de la propia aplicación.
- Redirección 301 de HTTP a HTTPS y desafío ACME para la renovación.
- Sin `Content-Security-Policy`: las páginas usan manejadores y scripts en línea; una CSP estricta las rompería. Queda para
  después de la entrega, empezando por `Content-Security-Policy-Report-Only`.
