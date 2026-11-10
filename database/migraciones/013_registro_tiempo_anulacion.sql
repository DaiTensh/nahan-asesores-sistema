-- Control de horas — anulación lógica de registros (D2)
--
-- Permite que un administrador anule un registro de horas erróneo SIN borrarlo: el registro original
-- (fechas, duración, tarifa, monto) queda intacto y se marca como anulado con quién, cuándo y por qué.
-- Los totales, informes y exportaciones lo excluyen; el historial de auditoría lo conserva.
--
-- Columnas nuevas de REGISTRO_TIEMPO:
--   estado_registro   VIGENTE (por defecto) o ANULADO. Todos los registros existentes quedan VIGENTE:
--                     no se reclasifica ni se pierde ningún dato.
--   anulado_por       usuario administrador que anuló (FK a USUARIO).
--   fecha_anulacion   fecha y hora de la anulación.
--   motivo_anulacion  texto obligatorio al anular.
--
-- Es solo aditiva. Son sentencias separadas para que, si una columna ya existe, las demás se agreguen
-- igual (migrar.py tolera «ya existe»). Aplíquela ANTES de reiniciar la aplicación con el código nuevo.
--
--     mysql -u <usuario> -p nahan_asesores < database/migraciones/013_registro_tiempo_anulacion.sql
--
-- Rollback manual (solo si no hay anulaciones que conservar; si las hay, respalde primero: se perdería
-- el motivo y el responsable, y los registros anulados volverían a sumar en los totales):
-- ALTER TABLE registro_tiempo DROP FOREIGN KEY fk_registro_tiempo_anulado_por;
-- ALTER TABLE registro_tiempo DROP COLUMN motivo_anulacion;
-- ALTER TABLE registro_tiempo DROP COLUMN fecha_anulacion;
-- ALTER TABLE registro_tiempo DROP COLUMN anulado_por;
-- ALTER TABLE registro_tiempo DROP COLUMN estado_registro;

ALTER TABLE registro_tiempo
    ADD COLUMN estado_registro ENUM('VIGENTE','ANULADO') NOT NULL DEFAULT 'VIGENTE';

ALTER TABLE registro_tiempo
    ADD COLUMN anulado_por INT NULL;

ALTER TABLE registro_tiempo
    ADD COLUMN fecha_anulacion DATETIME NULL;

ALTER TABLE registro_tiempo
    ADD COLUMN motivo_anulacion VARCHAR(255) NULL;

ALTER TABLE registro_tiempo
    ADD CONSTRAINT fk_registro_tiempo_anulado_por
        FOREIGN KEY (anulado_por) REFERENCES usuario(id_usuario);
