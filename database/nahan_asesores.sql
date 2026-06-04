DROP DATABASE IF EXISTS nahan_asesores;
CREATE DATABASE nahan_asesores
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE nahan_asesores;

CREATE TABLE rol (
    id_rol INT AUTO_INCREMENT PRIMARY KEY,
    nombre_rol VARCHAR(50) NOT NULL UNIQUE,
    descripcion VARCHAR(150),
    estado ENUM('ACTIVO','INACTIVO') NOT NULL DEFAULT 'ACTIVO'
);

CREATE TABLE area (
    id_area INT AUTO_INCREMENT PRIMARY KEY,
    nombre_area VARCHAR(100) NOT NULL UNIQUE,
    descripcion VARCHAR(150),
    estado ENUM('ACTIVO','INACTIVO') NOT NULL DEFAULT 'ACTIVO'
);

CREATE TABLE usuario (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    id_rol INT NOT NULL,
    id_area INT NOT NULL,
    nombres VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    estado ENUM('ACTIVO','INACTIVO') NOT NULL DEFAULT 'ACTIVO',
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_usuario_rol
        FOREIGN KEY (id_rol) REFERENCES rol(id_rol),

    CONSTRAINT fk_usuario_area
        FOREIGN KEY (id_area) REFERENCES area(id_area)
);

CREATE TABLE cliente (
    id_cliente INT AUTO_INCREMENT PRIMARY KEY,
    rut VARCHAR(20) NOT NULL UNIQUE,
    razon_social VARCHAR(200) NOT NULL,
    email VARCHAR(150),
    telefono VARCHAR(20),
    direccion VARCHAR(255),
    estado ENUM('ACTIVO','INACTIVO') NOT NULL DEFAULT 'ACTIVO',
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cliente_area (
    id_cliente_area INT AUTO_INCREMENT PRIMARY KEY,
    id_cliente INT NOT NULL,
    id_area INT NOT NULL,
    fecha_asignacion DATE NOT NULL,

    CONSTRAINT fk_cliente_area_cliente
        FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente),

    CONSTRAINT fk_cliente_area_area
        FOREIGN KEY (id_area) REFERENCES area(id_area),

    CONSTRAINT uq_cliente_area UNIQUE (id_cliente, id_area)
);

CREATE TABLE tarea (
    id_tarea INT AUTO_INCREMENT PRIMARY KEY,
    id_cliente INT NOT NULL,
    id_area INT NOT NULL,
    id_responsable INT NOT NULL,
    id_creador INT NOT NULL,
    titulo VARCHAR(200) NOT NULL,
    descripcion TEXT,
    estado ENUM('PENDIENTE','EN_PROCESO','EN_REVISION','COMPLETADA','CANCELADA') NOT NULL DEFAULT 'PENDIENTE',
    prioridad ENUM('BAJA','MEDIA','ALTA','URGENTE') NOT NULL DEFAULT 'MEDIA',
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_vencimiento DATE,
    fecha_inicio DATETIME,
    fecha_finalizacion DATETIME,
    observaciones TEXT,

    CONSTRAINT fk_tarea_cliente
        FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente),

    CONSTRAINT fk_tarea_area
        FOREIGN KEY (id_area) REFERENCES area(id_area),

    CONSTRAINT fk_tarea_responsable
        FOREIGN KEY (id_responsable) REFERENCES usuario(id_usuario),

    CONSTRAINT fk_tarea_creador
        FOREIGN KEY (id_creador) REFERENCES usuario(id_usuario)
);

CREATE TABLE documento (
    id_documento INT AUTO_INCREMENT PRIMARY KEY,
    id_cliente INT NOT NULL,
    nombre_documento VARCHAR(200) NOT NULL,
    url_archivo VARCHAR(255) NOT NULL,
    descripcion TEXT,
    fecha_subida DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    subido_por INT NOT NULL,
    estado ENUM('ACTIVO','INACTIVO') NOT NULL DEFAULT 'ACTIVO',

    CONSTRAINT fk_documento_cliente
        FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente),

    CONSTRAINT fk_documento_usuario
        FOREIGN KEY (subido_por) REFERENCES usuario(id_usuario)
);

CREATE TABLE tarea_documento (
    id_tarea_documento INT AUTO_INCREMENT PRIMARY KEY,
    id_tarea INT NOT NULL,
    id_documento INT NOT NULL,
    fecha_asociacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_tarea_documento_tarea
        FOREIGN KEY (id_tarea) REFERENCES tarea(id_tarea),

    CONSTRAINT fk_tarea_documento_documento
        FOREIGN KEY (id_documento) REFERENCES documento(id_documento),

    CONSTRAINT uq_tarea_documento UNIQUE (id_tarea, id_documento)
);

CREATE TABLE comentario_tarea (
    id_comentario INT AUTO_INCREMENT PRIMARY KEY,
    id_tarea INT NOT NULL,
    id_usuario INT NOT NULL,
    comentario TEXT NOT NULL,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_comentario_tarea
        FOREIGN KEY (id_tarea) REFERENCES tarea(id_tarea),

    CONSTRAINT fk_comentario_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);

CREATE TABLE revision_tarea (
    id_revision INT AUTO_INCREMENT PRIMARY KEY,
    id_tarea INT NOT NULL,
    id_revisor INT NOT NULL,
    accion VARCHAR(100) NOT NULL,
    observaciones TEXT,
    fecha_revision DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_revision_tarea
        FOREIGN KEY (id_tarea) REFERENCES tarea(id_tarea),

    CONSTRAINT fk_revision_usuario
        FOREIGN KEY (id_revisor) REFERENCES usuario(id_usuario)
);

CREATE TABLE notificacion (
    id_notificacion INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    mensaje TEXT NOT NULL,
    url_destino VARCHAR(255),
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    leida BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT fk_notificacion_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);

CREATE TABLE tiempo_trabajado (
    id_tiempo INT AUTO_INCREMENT PRIMARY KEY,
    id_tarea INT NOT NULL,
    id_usuario INT NOT NULL,
    fecha DATE NOT NULL,
    hora_inicio TIME NOT NULL,
    hora_fin TIME NOT NULL,
    horas_trabajadas DECIMAL(5,2) NOT NULL,
    descripcion VARCHAR(255),

    CONSTRAINT fk_tiempo_tarea
        FOREIGN KEY (id_tarea) REFERENCES tarea(id_tarea),

    CONSTRAINT fk_tiempo_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);

CREATE TABLE tarifa_hora (
    id_tarifa INT AUTO_INCREMENT PRIMARY KEY,
    id_area INT NOT NULL,
    valor_hora DECIMAL(10,2) NOT NULL,
    moneda VARCHAR(10) NOT NULL DEFAULT 'CLP',
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE,
    descripcion VARCHAR(255),
    estado ENUM('ACTIVA','INACTIVA') NOT NULL DEFAULT 'ACTIVA',

    CONSTRAINT fk_tarifa_area
        FOREIGN KEY (id_area) REFERENCES area(id_area)
);

CREATE TABLE cobro (
    id_cobro INT AUTO_INCREMENT PRIMARY KEY,
    id_cliente INT NOT NULL,
    id_tarea INT NOT NULL,
    id_tarifa INT NOT NULL,
    fecha DATE NOT NULL,
    horas_cobradas DECIMAL(5,2) NOT NULL,
    valor_hora DECIMAL(10,2) NOT NULL,
    monto_total DECIMAL(12,2) NOT NULL,
    moneda VARCHAR(10) NOT NULL DEFAULT 'CLP',
    estado ENUM('PENDIENTE','PAGADO','ANULADO') NOT NULL DEFAULT 'PENDIENTE',
    observaciones TEXT,

    CONSTRAINT fk_cobro_cliente
        FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente),

    CONSTRAINT fk_cobro_tarea
        FOREIGN KEY (id_tarea) REFERENCES tarea(id_tarea),

    CONSTRAINT fk_cobro_tarifa
        FOREIGN KEY (id_tarifa) REFERENCES tarifa_hora(id_tarifa)
);

CREATE TABLE reporte (
    id_reporte INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    tipo_reporte VARCHAR(50) NOT NULL,
    parametros JSON,
    fecha_generacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archivo_url VARCHAR(255),

    CONSTRAINT fk_reporte_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);

CREATE TABLE area_reporte (
    id_area_reporte INT AUTO_INCREMENT PRIMARY KEY,
    id_reporte INT NOT NULL,
    id_area INT NOT NULL,

    CONSTRAINT fk_area_reporte_reporte
        FOREIGN KEY (id_reporte) REFERENCES reporte(id_reporte),

    CONSTRAINT fk_area_reporte_area
        FOREIGN KEY (id_area) REFERENCES area(id_area),

    CONSTRAINT uq_area_reporte UNIQUE (id_reporte, id_area)
);

CREATE TABLE auditoria (
    id_auditoria INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    tabla_afectada VARCHAR(100) NOT NULL,
    accion VARCHAR(50) NOT NULL,
    datos_anteriores TEXT,
    datos_nuevos TEXT,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_auditoria_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
);

CREATE TABLE parametros_sistema (
    id_parametro INT AUTO_INCREMENT PRIMARY KEY,
    nombre_parametro VARCHAR(100) NOT NULL UNIQUE,
    valor_parametro VARCHAR(255) NOT NULL,
    tipo_dato VARCHAR(50) NOT NULL,
    descripcion VARCHAR(255)
);

CREATE INDEX idx_usuario_email ON usuario(email);
CREATE INDEX idx_cliente_rut ON cliente(rut);
CREATE INDEX idx_tarea_estado ON tarea(estado);
CREATE INDEX idx_tarea_responsable ON tarea(id_responsable);
CREATE INDEX idx_tarea_cliente ON tarea(id_cliente);
CREATE INDEX idx_documento_cliente ON documento(id_cliente);
CREATE INDEX idx_tiempo_tarea ON tiempo_trabajado(id_tarea);
CREATE INDEX idx_tiempo_usuario ON tiempo_trabajado(id_usuario);
CREATE INDEX idx_cobro_cliente ON cobro(id_cliente);
CREATE INDEX idx_cobro_estado ON cobro(estado);

INSERT INTO rol (nombre_rol, descripcion) VALUES
('ADMINISTRADOR', 'Usuario con acceso completo al sistema'),
('USUARIO_AREA_JURIDICA', 'Usuario perteneciente al área jurídica'),
('USUARIO_AREA_CONTABLE', 'Usuario perteneciente al área contable');

INSERT INTO area (nombre_area, descripcion) VALUES
('JURIDICA', 'Área encargada de procesos y asesorías jurídicas'),
('CONTABLE', 'Área encargada de procesos y asesorías contables'),
('ADMINISTRACION', 'Área administrativa interna');

INSERT INTO parametros_sistema (nombre_parametro, valor_parametro, tipo_dato, descripcion) VALUES
('NOMBRE_EMPRESA', 'Nahan Asesores', 'VARCHAR', 'Nombre de la empresa'),
('MONEDA_DEFAULT', 'CLP', 'VARCHAR', 'Moneda utilizada por defecto'),
('HORAS_JORNADA_DIARIA', '8', 'INT', 'Cantidad de horas referenciales por jornada');