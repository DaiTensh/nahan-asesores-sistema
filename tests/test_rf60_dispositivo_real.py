"""RF60 CA5 — El almacenamiento separado frente a un dispositivo realmente distinto.

Las pruebas de test_rf60_respaldos.py simulan el resultado de la comparación de
dispositivos. Estas usan un sistema de archivos distinto de verdad: en Linux,
`/dev/shm` (tmpfs); en cualquier equipo, el punto de montaje que indique
NAHAN_TEST_OTRO_DISPOSITIVO (un volumen, un disco externo o una imagen montada).
Si no hay un dispositivo distinto del de la aplicación, el módulo se omite: no
se simula ninguno.

Qué demuestran y qué no: el sistema compara números de dispositivo (st_dev), que
es lo máximo que puede afirmarse desde el sistema operativo. Un segundo volumen en
la misma instancia pasa esta prueba y, aun así, no es una copia fuera de la
instancia ni de la cuenta.
"""
import os
import shutil
import stat
import tempfile

import pytest

from backend.utils import respaldos as r
from tests.test_rf60_mysql_real import mundo, servidor  # noqa: F401  (fixtures compartidas)


def _otro_dispositivo():
    ruta = os.getenv("NAHAN_TEST_OTRO_DISPOSITIVO") or "/dev/shm"
    try:
        if os.path.isdir(ruta) and os.access(ruta, os.W_OK) and os.stat(ruta).st_dev != os.stat(r.RAIZ_PROYECTO).st_dev:
            return ruta
    except OSError:
        pass
    return None


OTRO = _otro_dispositivo()

pytestmark = pytest.mark.skipif(
    OTRO is None or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1" or not shutil.which("mysqldump"),
    reason="requiere un dispositivo distinto del de la aplicación (/dev/shm o NAHAN_TEST_OTRO_DISPOSITIVO) y mysqldump",
)


@pytest.fixture
def destino_separado():
    carpeta = tempfile.mkdtemp(prefix="nahan-respaldos-", dir=OTRO)
    yield os.path.join(carpeta, "paquetes")
    shutil.rmtree(carpeta, ignore_errors=True)


@pytest.fixture
def destino_en_el_mismo_disco():
    """Una carpeta fuera del proyecto pero en su mismo dispositivo: lo que pasa si el volumen no está montado."""
    carpeta = tempfile.mkdtemp(prefix="nahan-sin-montar-", dir=os.path.dirname(r.RAIZ_PROYECTO))
    yield os.path.join(carpeta, "paquetes")
    shutil.rmtree(carpeta, ignore_errors=True)


def _exigir(monkeypatch, destino):
    monkeypatch.setenv("RESPALDO_DIR", destino)
    monkeypatch.setenv("RESPALDO_EXIGIR_DISPOSITIVO_SEPARADO", "true")


def test_el_dispositivo_de_prueba_es_realmente_distinto_del_de_la_aplicacion(destino_separado):
    assert os.stat(os.path.dirname(destino_separado)).st_dev != os.stat(r.RAIZ_PROYECTO).st_dev


def test_un_destino_en_otro_dispositivo_se_reconoce_como_independiente(mundo, destino_separado, monkeypatch):
    _exigir(monkeypatch, destino_separado)

    evaluacion = r.evaluar_almacenamiento(r.ConfigRespaldo(), crear=True)

    assert evaluacion["apto"] is True and evaluacion["independiente"] is True
    independencia = next(v for v in evaluacion["verificaciones"] if v["clave"] == "independencia")
    assert independencia["nivel"] == "ok"
    assert stat.S_IMODE(os.stat(destino_separado).st_mode) == 0o700


def test_un_respaldo_completo_en_otro_dispositivo_queda_protegido_y_verificable(mundo, destino_separado, monkeypatch):
    _exigir(monkeypatch, destino_separado)

    resultado = r.ejecutar_respaldo("MANUAL", None)

    paquete = os.path.join(destino_separado, resultado["nombre_archivo"])
    assert os.stat(paquete).st_dev != os.stat(r.RAIZ_PROYECTO).st_dev
    assert stat.S_IMODE(os.stat(paquete).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(paquete + ".sha256").st_mode) == 0o600
    assert r.verificar_respaldo(resultado["id_respaldo"], None)["tablas"] == 22


def test_con_el_destino_sin_montar_el_respaldo_falla_en_lugar_de_escribir_en_el_disco_raiz(
    mundo, destino_en_el_mismo_disco, monkeypatch
):
    _exigir(monkeypatch, destino_en_el_mismo_disco)

    with pytest.raises(r.AlmacenamientoNoValido, match="mismo dispositivo"):
        r.ejecutar_respaldo("MANUAL", None)

    paquetes = [n for n in os.listdir(destino_en_el_mismo_disco) if n.endswith(".zip")] \
        if os.path.isdir(destino_en_el_mismo_disco) else []
    assert paquetes == [], "no debe quedar ningún paquete en el disco de la aplicación"


def test_sin_exigirlo_un_destino_en_el_mismo_disco_solo_avisa(mundo, destino_en_el_mismo_disco, monkeypatch):
    """Es el valor por defecto: por eso el servidor debe activar RESPALDO_EXIGIR_DISPOSITIVO_SEPARADO."""
    monkeypatch.setenv("RESPALDO_DIR", destino_en_el_mismo_disco)
    monkeypatch.delenv("RESPALDO_EXIGIR_DISPOSITIVO_SEPARADO", raising=False)

    evaluacion = r.evaluar_almacenamiento(r.ConfigRespaldo(), crear=True)

    assert evaluacion["apto"] is True and evaluacion["independiente"] is False
    assert next(v for v in evaluacion["verificaciones"] if v["clave"] == "independencia")["nivel"] == "aviso"
