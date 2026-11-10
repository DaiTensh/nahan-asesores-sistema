-- Usuarios — contraseña temporal con cambio obligatorio (migración 014)
--
-- El administrador crea cuentas y restablece contraseñas con una contraseña TEMPORAL: la persona debe
-- establecer una propia en su primer acceso. Se agregan dos columnas a USUARIO:
--
--   debe_cambiar_password  TRUE mientras la persona no haya establecido su contraseña personal. El servidor
--                          bloquea el resto de la API mientras esté en TRUE. Todas las cuentas existentes
--                          quedan en FALSE: conservan su comportamiento actual.
--   version_credenciales   Contador que sube cada vez que cambian las credenciales (cambio personal,
--                          restablecimiento por el administrador o por enlace de correo). La sesión guarda
--                          la versión con la que se abrió: si no coincide con la de la base, deja de valer.
--                          Así se invalidan las sesiones anteriores sin una tabla de sesiones.
--
-- Solo agrega columnas: no toca usuarios, hashes ni datos. Son dos sentencias separadas para que, si una
-- columna ya existe, la otra se agregue igual (migrar.py tolera «ya existe»).
--
--     mysql -u <usuario> -p nahan_asesores < database/migraciones/014_usuario_cambio_password_obligatorio.sql
--
-- Aplíquela ANTES de reiniciar con el código nuevo (el código consulta estas columnas).
--
-- Rollback manual (el código anterior ignora las columnas; quitarlas pierde qué cuentas tenían el cambio
-- pendiente y deja de invalidar sesiones antiguas):
-- ALTER TABLE usuario DROP COLUMN version_credenciales;
-- ALTER TABLE usuario DROP COLUMN debe_cambiar_password;

ALTER TABLE usuario
    ADD COLUMN debe_cambiar_password BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE usuario
    ADD COLUMN version_credenciales INT NOT NULL DEFAULT 0;
