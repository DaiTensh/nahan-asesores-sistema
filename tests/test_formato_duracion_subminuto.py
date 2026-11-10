"""P3 (auditoría 9-nov): 16 s con cobro asociado se mostraban como «00h 00m».

El dato guardado (0,27 min) y el monto eran correctos; solo la presentación
redondeaba a cero. Se comprueba el formateador real extrayéndolo con Node.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="Node no disponible")


def _formatear(archivo, funcion, valor):
    codigo = open(os.path.join(RAIZ, archivo), encoding="utf-8").read()
    m = re.search(r"function %s\(.*?\n}\n" % funcion, codigo, re.S)
    assert m, funcion
    extra = "function rellenar(n){return String(n).padStart(2,'0');}"
    salida = subprocess.run(
        ["node", "-e", f"{extra}\n{m.group(0)}\nconsole.log(JSON.stringify({funcion}({json.dumps(valor)})))"],
        capture_output=True, text=True, check=True).stdout
    return json.loads(salida)


@pytest.mark.parametrize("archivo,funcion", [
    ("frontend/control_horas/control_horas.js", "formatearMinutos"),
    ("frontend/tareas/detalle_tarea.js", "formatearMinutosTarea"),
])
@pytest.mark.parametrize("valor,esperado", [
    (0.27, "< 1 min"), ("0.27", "< 1 min"), (0, "00h 00m"), (None, "00h 00m"),
    (0.5, "00h 01m"), (90, "01h 30m"), (3107.97, "51h 48m"),
])
def test_formato_duracion(archivo, funcion, valor, esperado):
    assert _formatear(archivo, funcion, valor) == esperado
