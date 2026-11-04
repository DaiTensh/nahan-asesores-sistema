-- RF60 — Respaldando históricamente la información (Incremento 4)
--
-- Historial de respaldos y restauraciones: fecha, hora, tipo de ejecución,
-- estado y resultado de cada operación (CA3). No guarda contraseñas ni rutas
-- absolutas: solo el nombre del paquete dentro de RESPALDO_DIR.
--
--   operacion   RESPALDO | RESTAURACION.
--   tipo        MANUAL (administrador), PROGRAMADO (nahan-respaldo.timer) o
--               PREVIO_RESTAURACION (copia de seguridad que se toma antes de
--               restaurar).
--   id_relacionado  RESTAURACION: respaldo que se restauró.
--                   PREVIO_RESTAURACION: restauración que lo originó.
--   id_usuario  Sin clave foránea a propósito: una restauración puede dejar la
--               tabla usuario como estaba en el respaldo, y este historial debe
--               sobrevivir a eso. NULL en los respaldos programados.
--
-- Esta tabla NO forma parte de los paquetes de respaldo (el dump la excluye):
-- así el historial persiste cuando se restaura un respaldo antiguo.
--
-- Rollback manual (elimina el historial de respaldos):
-- DROP TABLE respaldo;

CREATE TABLE respaldo (
    id_respaldo INT AUTO_INCREMENT PRIMARY KEY,
    operacion ENUM('RESPALDO','RESTAURACION') NOT NULL DEFAULT 'RESPALDO',
    tipo ENUM('MANUAL','PROGRAMADO','PREVIO_RESTAURACION') NOT NULL,
    estado ENUM('EN_CURSO','EXITOSO','FALLIDO') NOT NULL DEFAULT 'EN_CURSO',
    fecha_inicio DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin DATETIME NULL,
    duracion_segundos DECIMAL(10,2) NULL,
    id_usuario INT NULL,
    id_relacionado INT NULL,
    nombre_archivo VARCHAR(120) NULL,
    tamano_bytes BIGINT NULL,
    sha256 CHAR(64) NULL,
    detalle VARCHAR(500) NULL,
    mensaje_error VARCHAR(500) NULL,
    archivo_eliminado_en DATETIME NULL,

    INDEX idx_respaldo_fecha (fecha_inicio, id_respaldo),
    INDEX idx_respaldo_estado (estado, operacion)
);
