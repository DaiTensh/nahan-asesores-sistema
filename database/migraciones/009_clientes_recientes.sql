-- RF47: últimas fichas consultadas por usuario.
-- Rollback manual (elimina las interacciones nuevas):
-- DROP TABLE cliente_reciente;
-- DELETE FROM parametros_sistema WHERE nombre_parametro = 'CLIENTES_RECIENTES_LIMITE';

CREATE TABLE cliente_reciente (
    id_usuario INT NOT NULL,
    id_cliente INT NOT NULL,
    fecha_interaccion DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),

    PRIMARY KEY (id_usuario, id_cliente),
    INDEX idx_cliente_reciente_usuario_fecha (id_usuario, fecha_interaccion DESC, id_cliente DESC),
    CONSTRAINT fk_cliente_reciente_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario) ON DELETE CASCADE,
    CONSTRAINT fk_cliente_reciente_cliente
        FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente) ON DELETE CASCADE
);

INSERT IGNORE INTO parametros_sistema (nombre_parametro, valor_parametro, tipo_dato, descripcion)
VALUES ('CLIENTES_RECIENTES_LIMITE', '5', 'INT', 'Máximo global de clientes recientes mostrados por usuario');