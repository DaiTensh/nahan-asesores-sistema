-- RF59 — Cerrando Automático por Inactividad (Incremento 3)
--
-- Parámetros configurables por el administrador desde
-- «Administración › Configuración de sesión»:
--   SESION_INACTIVIDAD_MINUTOS: minutos sin actividad antes de cerrar la sesión.
--   SESION_AVISO_SEGUNDOS: segundos de anticipación con que se muestra el aviso.
--
-- Migración para bases creadas antes del Incremento 3. Quien importe
-- database/nahan_asesores.sql desde cero no necesita ejecutarla.
--
--     mysql -u <usuario> -p nahan_asesores < database/migraciones/006_parametros_sesion.sql

INSERT IGNORE INTO parametros_sistema (nombre_parametro, valor_parametro, tipo_dato, descripcion) VALUES
('SESION_INACTIVIDAD_MINUTOS', '30', 'INT', 'Minutos de inactividad antes de cerrar la sesión automáticamente'),
('SESION_AVISO_SEGUNDOS', '60', 'INT', 'Segundos de anticipación con que se avisa el cierre por inactividad');
