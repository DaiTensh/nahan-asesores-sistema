-- RF54 — Adjuntando Archivos a Tareas
--
-- Migración para bases que ya fueron creadas antes del Incremento 2. Quien
-- importe database/nahan_asesores.sql desde cero no necesita ejecutarla: los
-- parámetros ya vienen incluidos en el seed.
--
--     mysql -u <usuario> -p nahan_asesores < database/migraciones/002_parametros_adjuntos.sql
--
-- Límite de tamaño y lista blanca de extensiones para los adjuntos de tarea,
-- configurables sin tocar código.

INSERT IGNORE INTO parametros_sistema (nombre_parametro, valor_parametro, tipo_dato, descripcion) VALUES
('ADJUNTOS_TAMANO_MAXIMO_MB', '10', 'INT', 'Tamaño máximo, en MB, de un archivo adjunto a una tarea'),
('ADJUNTOS_EXTENSIONES_PERMITIDAS', 'pdf,doc,docx,xls,xlsx,ppt,pptx,jpg,jpeg,png', 'VARCHAR', 'Extensiones permitidas para adjuntos de tarea, separadas por coma');
