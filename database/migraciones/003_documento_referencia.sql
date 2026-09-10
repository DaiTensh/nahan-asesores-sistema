-- RF07 — Registrando Referencias a Documentos de Clientes
--
-- Migración para bases que ya fueron creadas antes del Incremento 2. Quien
-- importe database/nahan_asesores.sql desde cero no necesita ejecutarla: la
-- columna y la restricción ya vienen incluidas en el esquema.
--
--     mysql -u <usuario> -p nahan_asesores < database/migraciones/003_documento_referencia.sql
--
-- Agrega el tipo de documento para las referencias que registra RF07. La
-- columna queda opcional para no romper los adjuntos de tarea que ya inserta
-- RF54 (Iván) sin ese dato. El UNIQUE evita repetir la misma referencia
-- (nombre + ubicación) para un mismo cliente.

ALTER TABLE documento
    ADD COLUMN tipo_documento VARCHAR(60) AFTER nombre_documento;

ALTER TABLE documento
    ADD CONSTRAINT uq_documento_referencia UNIQUE (id_cliente, nombre_documento, url_archivo);
