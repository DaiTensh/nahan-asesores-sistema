"""Validación de los datos de contacto de un cliente (RF01 y RF04).

No se comprueba el dígito verificador del RUT: parte de los datos de
demostración y de las pruebas usa RUT de ejemplo que no lo cumplen. Sí se
exige el formato y se normaliza, para que «12345678-5» y «12.345.678-5» no se
registren como dos clientes distintos.
"""
import re

_RUT = re.compile(r"^([0-9]{1,2})\.?([0-9]{3})\.?([0-9]{3})-?([0-9kK])\Z")
_CORREO = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+\Z")
_TELEFONO = re.compile(r"^\+?[0-9(][0-9 ()\-.]{5,19}\Z")

MENSAJE_RUT = "El RUT no tiene un formato válido (ejemplo: 12.345.678-5)."
MENSAJE_CORREO = "El correo electrónico no tiene un formato válido."
MENSAJE_TELEFONO = "El teléfono no tiene un formato válido (solo números, espacios, «+», «-» y paréntesis)."


def normalizar_rut(texto):
    """RUT en formato canónico «12.345.678-5», o None si el formato no es válido."""
    coincidencia = _RUT.match((texto or "").strip())
    if not coincidencia:
        return None
    cuerpo, grupo2, grupo3, digito = coincidencia.groups()
    return f"{int(cuerpo)}.{grupo2}.{grupo3}-{digito.upper()}"


def rut_comparable(rut_canonico):
    """Forma sin puntos ni guion para comparar contra RUT guardados con otro formato."""
    return rut_canonico.replace(".", "").replace("-", "").upper()


def error_de_contacto(email, telefono):
    """Mensaje de error para un correo o teléfono informados con mal formato, o None."""
    if email and (len(email) > 150 or not _CORREO.match(email)):
        return MENSAJE_CORREO
    if telefono and not _TELEFONO.match(telefono):
        return MENSAJE_TELEFONO
    return None
