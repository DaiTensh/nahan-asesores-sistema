"""RF54: el contenido de un adjunto debe corresponder a su extensión, y su nombre caber en la base."""
import pytest

from backend.utils.firmas_archivo import contenido_corresponde_a_extension as coincide

PDF = b"%PDF-1.7\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 8
JPG = b"\xff\xd8\xff\xe0" + b"0" * 8
ZIP = b"PK\x03\x04" + b"0" * 8
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 8


@pytest.mark.parametrize("extension,cabecera", [
    ("pdf", PDF), ("PDF", PDF), ("pdf", b"\n\n  " + PDF), ("png", PNG), ("jpg", JPG), ("jpeg", JPG),
    ("docx", ZIP), ("xlsx", ZIP), ("pptx", ZIP), ("doc", OLE), ("xls", OLE), ("ppt", OLE),
    ("txt", b"cualquier cosa"), ("csv", b""), ("", b"x"), (None, b"x"),
])
def test_contenidos_que_corresponden_a_su_extension(extension, cabecera):
    assert coincide(extension, cabecera)


@pytest.mark.parametrize("extension,cabecera", [
    ("pdf", b"MZ\x90\x00"), ("pdf", b"esto no es un pdf"), ("pdf", b""), ("pdf", b"x" * 2000 + PDF),
    ("png", JPG), ("jpg", PNG), ("jpeg", PDF), ("docx", OLE), ("xlsx", PDF), ("doc", ZIP), ("xls", b"<html>"),
])
def test_contenidos_que_no_corresponden_a_su_extension(extension, cabecera):
    assert not coincide(extension, cabecera)

