-- RF56 — Historiando la Actividad (Incremento 3)
--
-- Agrega a AUDITORIA la columna id_registro: el identificador del registro
-- afectado dentro de tabla_afectada (id_tarea, id_cliente, id_documento,
-- id_usuario, ...). Con ella el historial global (RF56), el consolidado
-- (RF40), el historial por cliente (RF13), el historial por usuario (RF30) y
-- el flujo de revisión (RF76) consultan la auditoría sin interpretar el texto
-- libre de datos_anteriores / datos_nuevos.
--
-- Migración para bases creadas antes del Incremento 3. Quien importe
-- database/nahan_asesores.sql desde cero no necesita ejecutarla.
--
--     mysql -u <usuario> -p nahan_asesores < database/migraciones/005_auditoria_id_registro.sql

ALTER TABLE auditoria
    ADD COLUMN id_registro INT NULL AFTER tabla_afectada;

CREATE INDEX idx_auditoria_tabla_registro ON auditoria (tabla_afectada, id_registro);
CREATE INDEX idx_auditoria_usuario_fecha ON auditoria (id_usuario, fecha);
CREATE INDEX idx_auditoria_fecha ON auditoria (fecha);

-- Filas anteriores a esta migración: se recupera el identificador desde el
-- texto que ya guardaban las rutas de tareas ("id_tarea=N, ...") y la
-- descarga de adjuntos ("id_documento=N"). Las filas de cliente del
-- Incremento 1 no incluían el id en el texto, por lo que quedan en NULL.
UPDATE auditoria
   SET id_registro = CAST(REGEXP_SUBSTR(REGEXP_SUBSTR(COALESCE(datos_nuevos, datos_anteriores), 'id_tarea=[0-9]+'), '[0-9]+') AS UNSIGNED)
 WHERE tabla_afectada = 'tarea'
   AND id_registro IS NULL
   AND COALESCE(datos_nuevos, datos_anteriores) REGEXP 'id_tarea=[0-9]+';

UPDATE auditoria
   SET id_registro = CAST(REGEXP_SUBSTR(REGEXP_SUBSTR(datos_nuevos, 'id_documento=[0-9]+'), '[0-9]+') AS UNSIGNED)
 WHERE tabla_afectada = 'documento'
   AND id_registro IS NULL
   AND datos_nuevos REGEXP 'id_documento=[0-9]+';
