import secrets

import bcrypt

def hash_password(password):
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def check_password(password, password_hash):
    password_bytes = password.encode("utf-8")
    hash_bytes = password_hash.encode("utf-8")
    try:
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except ValueError:
        return False

# Largo mínimo de una contraseña nueva (restablecimiento y alta de usuarios).
LARGO_MINIMO_PASSWORD = 8

# Largo máximo que bcrypt procesa (el resto se ignoraría en silencio).
LARGO_MAXIMO_PASSWORD_BYTES = 72

# Sin caracteres ambiguos (0/O, 1/l/I) para que se pueda dictar o copiar sin errores.
_ALFABETO_TEMPORAL = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
LARGO_PASSWORD_TEMPORAL = 14


def generar_password_temporal():
    """Contraseña temporal aleatoria (14 caracteres, ~80 bits) con el módulo `secrets`.

    Cumple la política vigente (mínimo 8, máximo 72 bytes). Quien la genera decide cómo entregarla:
    nunca debe guardarse en texto plano, auditarse, registrarse en logs ni viajar en una URL.
    """
    while True:
        candidata = "".join(secrets.choice(_ALFABETO_TEMPORAL) for _ in range(LARGO_PASSWORD_TEMPORAL))
        # Al menos una mayúscula, una minúscula y un dígito (mejor lectura y política habitual).
        if (any(c.isupper() for c in candidata) and any(c.islower() for c in candidata)
                and any(c.isdigit() for c in candidata)):
            return candidata


def error_de_password_nueva(password):
    """None si la contraseña cumple la política vigente; si no, el mensaje de error."""
    if not isinstance(password, str) or len(password) < LARGO_MINIMO_PASSWORD:
        return f"La contraseña debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres"
    if len(password.encode("utf-8")) > LARGO_MAXIMO_PASSWORD_BYTES:
        return f"La contraseña no puede superar {LARGO_MAXIMO_PASSWORD_BYTES} bytes UTF-8"
    return None
