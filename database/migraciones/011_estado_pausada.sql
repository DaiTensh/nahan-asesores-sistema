-- RF17 — Actualizando el Estado de Tareas: estado «Pausada» (Incremento 4)
--
-- El texto oficial pide poder pasar una tarea entre pendiente, en proceso,
-- pausada o finalizada. Se agrega PAUSADA al final de la lista de valores de
-- tarea.estado: los valores y las tareas existentes no cambian, y MySQL lo aplica
-- sin reconstruir la tabla. Es seguro ejecutarla más de una vez.
--
-- Migración para bases creadas antes del Incremento 4. Quien importe
-- database/nahan_asesores.sql desde cero no necesita ejecutarla.
--
--     mysql -u <usuario> -p nahan_asesores < database/migraciones/011_estado_pausada.sql

ALTER TABLE tarea MODIFY COLUMN estado
    ENUM('PENDIENTE','EN_PROCESO','EN_REVISION','COMPLETADA','CANCELADA','PAUSADA')
    NOT NULL DEFAULT 'PENDIENTE';
