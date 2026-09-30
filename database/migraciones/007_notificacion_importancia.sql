-- RF46 — Alertando y Notificando (Incremento 3)
--
-- Agrega a NOTIFICACION la columna importancia: NORMAL, ALTA o CRITICA. Las
-- notificaciones existentes quedan en NORMAL, de modo que no se pierde ni se
-- reclasifica ningún dato. Las críticas se destacan en la bandeja.
--
-- Migración para bases creadas antes del Incremento 3. Quien importe
-- database/nahan_asesores.sql desde cero no necesita ejecutarla.
--
--     mysql -u <usuario> -p nahan_asesores < database/migraciones/007_notificacion_importancia.sql

ALTER TABLE notificacion
    ADD COLUMN importancia VARCHAR(10) NOT NULL DEFAULT 'NORMAL' AFTER tipo;
