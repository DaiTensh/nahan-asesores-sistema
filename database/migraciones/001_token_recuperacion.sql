-- RF26 — Restableciendo Contraseñas
--
-- Migración para bases que ya fueron creadas antes del Incremento 2. Quien
-- importe database/nahan_asesores.sql desde cero no necesita ejecutarla: la
-- tabla ya viene incluida en el esquema.
--
--     mysql -u <usuario> -p nahan_asesores < database/migraciones/001_token_recuperacion.sql
--
-- Se almacena el hash SHA-256 del token, no el token en claro: si la base se
-- filtrara, los enlaces de restablecimiento vigentes seguirían siendo
-- inservibles para quien los obtenga.

CREATE TABLE IF NOT EXISTS token_recuperacion (
    id_token INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    fecha_emision DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_expiracion DATETIME NOT NULL,
    utilizado BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_uso DATETIME,

    CONSTRAINT fk_token_recuperacion_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);
