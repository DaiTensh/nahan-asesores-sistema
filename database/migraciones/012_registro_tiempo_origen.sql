-- Control de horas — registro manual de horas (Incremento 4)
--
-- Permite ingresar a mano el tiempo trabajado cuando no se pudo usar el
-- temporizador (casos de uso CU-14 y CU-29). Agrega a REGISTRO_TIEMPO dos
-- columnas:
--
--   origen       TEMPORIZADOR o MANUAL. Los registros que ya existen quedan en
--                TEMPORIZADOR: no se pierde ni se reclasifica ningún dato.
--   observacion  Texto con el trabajo realizado. Solo lo llenan los registros
--                manuales; en los del temporizador queda en NULL.
--
-- Son dos sentencias separadas para que, si una de las columnas ya existe, la otra
-- se agregue igual (migrar.py tolera el error «la columna ya existe»).
--
-- Migración para bases creadas antes de esta versión. Quien importe
-- database/nahan_asesores.sql desde cero no necesita ejecutarla.
--
--     mysql -u <usuario> -p nahan_asesores < database/migraciones/012_registro_tiempo_origen.sql
--
-- Rollback manual (solo si todavía no se registraron horas manuales que se quieran conservar):
-- ALTER TABLE registro_tiempo DROP COLUMN observacion;
-- ALTER TABLE registro_tiempo DROP COLUMN origen;

ALTER TABLE registro_tiempo
    ADD COLUMN origen ENUM('TEMPORIZADOR','MANUAL') NOT NULL DEFAULT 'TEMPORIZADOR';

ALTER TABLE registro_tiempo
    ADD COLUMN observacion VARCHAR(255) NULL;
