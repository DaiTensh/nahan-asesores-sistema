-- RF09 — Registrando Observaciones Internas de Clientes
--
-- Migración para bases que ya fueron creadas antes del Incremento 2. Quien
-- importe database/nahan_asesores.sql desde cero no necesita ejecutarla: la
-- tabla ya viene incluida en el esquema.
--
--     mysql -u <usuario> -p nahan_asesores < database/migraciones/004_observacion_cliente.sql
--
-- Visibles solo para el staff operativo (ADMINISTRADOR, JURIDICA, CONTABLE),
-- igual que el resto de los datos de la ficha del cliente.

CREATE TABLE IF NOT EXISTS observacion_cliente (
    id_observacion INT AUTO_INCREMENT PRIMARY KEY,
    id_cliente INT NOT NULL,
    id_usuario INT NOT NULL,
    texto TEXT NOT NULL,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_observacion_cliente_cliente
        FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente),

    CONSTRAINT fk_observacion_cliente_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);

CREATE INDEX idx_observacion_cliente_cliente ON observacion_cliente(id_cliente);
