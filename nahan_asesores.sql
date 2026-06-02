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