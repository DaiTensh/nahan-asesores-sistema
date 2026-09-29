"""Preparación de la base local: migraciones pendientes e instalador.

Pruebas sin MySQL: la conexión y el cursor se simulan.
"""
import os
import sys
from types import SimpleNamespace

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "database"))

import migrar  # noqa: E402


class ErrorMySQL(Exception):
    def __init__(self, errno):
        super().__init__(f"error {errno}")
        self.errno = errno


class CursorMarcadores:
    """Responde a los marcadores según un conjunto de objetos «existentes»."""

    def __init__(self, existentes):
        self.existentes = existentes
        self.ultimo = 0

    def execute(self, sql, params=()):
        self.ultimo = 1 if tuple(params) in self.existentes else 0

    def fetchone(self):
        return (self.ultimo,)


def test_migraciones_en_orden_y_con_marcador():
    numeros = [n for n, _, _ in migrar.migraciones()]
    assert numeros == sorted(numeros)
    assert numeros[:6] == ["001", "002", "003", "004", "005", "006"]
    for n in numeros:
        assert n in migrar.MARCADORES, f"la migración {n} no tiene marcador"


def test_sentencias_ignora_comentarios():
    ruta = os.path.join(migrar.CARPETA, "005_auditoria_id_registro.sql")
    lista = migrar.sentencias(ruta)
    assert lista[0].startswith("ALTER TABLE auditoria")
    assert not any(s.lstrip().startswith("--") for s in lista)
    assert len(lista) == 6


def test_pendientes_detecta_lo_que_falta():
    todo = set()
    for consultas in migrar.MARCADORES.values():
        for _, params in consultas:
            todo.add(tuple(params))
    assert migrar.pendientes(CursorMarcadores(todo)) == []

    sin_005 = {p for p in todo if p != ("auditoria", "id_registro")}
    assert migrar.pendientes(CursorMarcadores(sin_005)) == ["005"]


def test_aplicar_tolera_ya_existe_y_propaga_otros_errores(monkeypatch, tmp_path):
    connector = SimpleNamespace(Error=ErrorMySQL)
    monkeypatch.setitem(sys.modules, "mysql", SimpleNamespace(connector=connector))
    monkeypatch.setitem(sys.modules, "mysql.connector", connector)

    archivo = tmp_path / "007_prueba.sql"
    archivo.write_text("-- comentario; con punto y coma\nALTER TABLE a ADD COLUMN b INT;\nCREATE INDEX i ON a (b);\n",
                       encoding="utf-8")

    def conexion(errores):
        ejecutadas = []

        def execute(sql):
            ejecutadas.append(sql)
            if errores:
                raise ErrorMySQL(errores.pop(0))

        cur = SimpleNamespace(execute=execute, nextset=lambda: False, close=lambda: None)
        cn = SimpleNamespace(cursor=lambda: cur, commits=0)
        cn.commit = lambda: setattr(cn, "commits", cn.commits + 1)
        return cn, ejecutadas

    cn, ejecutadas = conexion([1060, 1061])
    assert migrar.aplicar(cn, str(archivo)) == 2
    assert len(ejecutadas) == 2 and cn.commits == 1

    cn, _ = conexion([1146])
    with pytest.raises(ErrorMySQL):
        migrar.aplicar(cn, str(archivo))
    assert cn.commits == 0


def test_setup_crea_tablas_en_base_existente_vacia(monkeypatch):
    from scripts import setup

    cfg = {"DB_HOST": "localhost", "DB_PORT": "3306", "DB_USER": "prueba",
           "DB_PASSWORD": "", "DB_NAME": "nahan_prueba"}
    monkeypatch.setattr(setup, "conectar", lambda *a: SimpleNamespace(returncode=0, stdout="OK"))
    codigos = []

    def correr(cmd):
        codigo = cmd[-1]
        codigos.append(codigo)
        if "SELECT SCHEMA_NAME" in codigo:
            return SimpleNamespace(returncode=0, stdout="EXISTE 0")
        if "sql = open(" in codigo:
            return SimpleNamespace(returncode=0, stdout="SENTENCIAS 41")
        return SimpleNamespace(returncode=0, stdout="TABLAS 21")

    monkeypatch.setattr(setup, "correr", correr)
    monkeypatch.setattr(setup, "confirmar_borrado", lambda *a: pytest.fail("No debe preparar borrado"))
    assert setup.importar_esquema(cfg) is True
    importacion = next(c for c in codigos if "sql = open(" in c)
    assert "CREATE DATABASE IF NOT EXISTS" in importacion


def test_setup_conserva_base_con_tablas(monkeypatch):
    from scripts import setup

    cfg = {"DB_HOST": "localhost", "DB_PORT": "3306", "DB_USER": "prueba",
           "DB_PASSWORD": "", "DB_NAME": "nahan_prueba"}
    monkeypatch.setattr(setup, "conectar", lambda *a: SimpleNamespace(returncode=0, stdout="OK"))
    monkeypatch.setattr(setup, "correr", lambda cmd: SimpleNamespace(returncode=0, stdout="EXISTE 21"))
    monkeypatch.setattr(setup, "confirmar_borrado", lambda *a: pytest.fail("No debe preparar borrado"))
    assert setup.importar_esquema(cfg) is False


@pytest.mark.parametrize("salida,esperado", [
    ("ERROR 2003 (HY000): Can't connect to MySQL server on 'localhost:3306' (10061)", "No es un problema de"),
    ("ERROR 1045 (28000): Access denied for user", "DB_PASSWORD"),
])
def test_setup_explica_error_de_conexion(salida, esperado):
    from scripts import setup
    assert esperado in setup.explicar_error_mysql(salida, {"DB_HOST": "localhost", "DB_PORT": "3306"})
