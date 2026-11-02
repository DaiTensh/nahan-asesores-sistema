"""Comprobación de que el contenido de un adjunto corresponde a su extensión (RF54).

La extensión sola la elige quien sube el archivo: un ejecutable renombrado a
«.pdf» pasaría. Se comparan los primeros bytes con la firma del formato. Las
extensiones sin firma conocida (las que el administrador agregue a
ADJUNTOS_EXTENSIONES_PERMITIDAS) no se comprueban.
"""

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP = b"PK\x03\x04"

_FIRMAS = {
    "pdf": lambda cabecera: b"%PDF-" in cabecera[:1024],
    "png": lambda cabecera: cabecera.startswith(b"\x89PNG\r\n\x1a\n"),
    "jpg": lambda cabecera: cabecera.startswith(b"\xff\xd8\xff"),
    "jpeg": lambda cabecera: cabecera.startswith(b"\xff\xd8\xff"),
    "docx": lambda cabecera: cabecera.startswith(_ZIP),
    "xlsx": lambda cabecera: cabecera.startswith(_ZIP),
    "pptx": lambda cabecera: cabecera.startswith(_ZIP),
    "doc": lambda cabecera: cabecera.startswith(_OLE),
    "xls": lambda cabecera: cabecera.startswith(_OLE),
    "ppt": lambda cabecera: cabecera.startswith(_OLE),
}

BYTES_A_LEER = 1024


def contenido_corresponde_a_extension(extension, cabecera):
    """True si no hay firma conocida para la extensión o si la cabecera la cumple."""
    comprobar = _FIRMAS.get((extension or "").lower())
    return True if comprobar is None else bool(comprobar(cabecera))
