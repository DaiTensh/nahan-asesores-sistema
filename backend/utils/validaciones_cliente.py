"""Validación de los datos de contacto de un cliente (RF01 y RF04).

El RUT se valida con el dígito verificador (módulo 11) y se normaliza a
«12.345.678-5»: así «12345678-5» y «12.345.678-5» no se registran como dos
clientes distintos. La misma regla está en frontend/assets/js/rut.js para avisar
antes de enviar el formulario; el servidor es quien decide.
"""
import re

_RUT = re.compile(r"^([0-9]{1,2})\.?([0-9]{3})\.?([0-9]{3})-?([0-9kK])\Z")
_CORREO = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+\Z")
_TELEFONO = re.compile(r"^\+?[0-9(][0-9 ()\-.]{5,19}\Z")

RUT_MINIMO = 1_000_000
MENSAJE_RUT = "El RUT no tiene un formato válido (ejemplo: 12.345.678-5)."
MENSAJE_RUT_DIGITO = "El RUT no es válido: revise el número y el dígito verificador."
MENSAJE_CORREO = "El correo electrónico no tiene un formato válido."
MENSAJE_TELEFONO = "El teléfono no tiene un formato válido (solo números, espacios, «+», «-» y paréntesis)."


def normalizar_rut(texto):
    """RUT en formato canónico «12.345.678-5», o None si el formato no es válido."""
    coincidencia = _RUT.match((texto or "").strip())
    if not coincidencia:
        return None
    cuerpo, grupo2, grupo3, digito = coincidencia.groups()
    return f"{int(cuerpo)}.{grupo2}.{grupo3}-{digito.upper()}"


def calcular_digito_verificador(cuerpo):
    """Dígito verificador chileno (módulo 11) de un RUT sin puntos ni guion: «0»–«9» o «K»."""
    suma, factor = 0, 2
    for cifra in reversed(str(int(cuerpo))):
        suma += int(cifra) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return "0" if resto == 11 else "K" if resto == 10 else str(resto)


def validar_rut(texto):
    """(rut_canonico, None) si el RUT es válido; (None, mensaje) si no lo es."""
    canonico = normalizar_rut(texto)
    if canonico is None:
        return None, MENSAJE_RUT
    cuerpo, digito = rut_comparable(canonico)[:-1], canonico[-1]
    if int(cuerpo) < RUT_MINIMO or calcular_digito_verificador(cuerpo) != digito:
        return None, MENSAJE_RUT_DIGITO
    return canonico, None


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
