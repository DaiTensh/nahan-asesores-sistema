-- SEC-02 — Límite de intentos fallidos de inicio de sesión
--
-- Una fila = un intento de inicio de sesión que consume cuota: se inserta
-- antes de comprobar la contraseña, se conserva si el intento falla y se
-- borra si el inicio de sesión tiene éxito. Los éxitos no se registran.
-- Las filas se purgan pasadas 24 horas (backend/utils/limitador_login.py).
--
-- No guarda contraseñas ni correos: clave_cuenta es un HMAC-SHA256 del correo
-- canónico y ip_cliente es la IPv4 completa (4 bytes) o el prefijo /64 de una
-- IPv6 (8 bytes), o NULL si la IP del cliente no es fiable. id_usuario sirve
-- solo para el desbloqueo operativo (DELETE ... WHERE id_usuario = ?). Sin
-- claves foráneas, a propósito: no deben bloquear filas de usuario.
--
-- Migración para bases creadas antes de SEC-02. Quien importe
-- database/nahan_asesores.sql desde cero no necesita ejecutarla.
--
--     mysql -u <usuario> -p nahan_asesores < database/migraciones/008_intento_login_fallido.sql

CREATE TABLE IF NOT EXISTS intento_login_fallido (
    id_intento BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    clave_cuenta BINARY(32) NOT NULL,
    ip_cliente VARBINARY(16) NULL,
    id_usuario INT NULL,
    fecha DATETIME NOT NULL,

    PRIMARY KEY (id_intento),
    KEY idx_ilf_cuenta (clave_cuenta, fecha),
    KEY idx_ilf_ip (ip_cliente, fecha),
    KEY idx_ilf_fecha (fecha)
) ENGINE=InnoDB;
