"""RF60 — Respaldando históricamente la información: servicio de respaldo.

Pruebas sin MySQL: el volcado se simula y el historial vive en memoria. El
recorrido completo contra un servidor MySQL real está en
test_rf60_mysql_real.py.
"""
import hashlib
import json
import os
import stat
import subprocess
import threading
import time
import zipfile
from types import SimpleNamespace

import pytest

from backend.utils import respaldos as r

CLAVE_SECRETA = "clave-secreta-ficticia"

VOLCADO_BASE = """-- MySQL dump 10.13  Distrib 8.0.46, for Linux (x86_64)
--
-- Host: 127.0.0.1    Database: base_ficticia
-- ------------------------------------------------------
-- Server version\t8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;

--
-- Table structure for table `cliente`
--

DROP TABLE IF EXISTS `cliente`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cliente` (
  `id_cliente` int NOT NULL AUTO_INCREMENT,
  `razon_social` varchar(200) NOT NULL,
  PRIMARY KEY (`id_cliente`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

LOCK_PLACEHOLDER/*!40000 ALTER TABLE `cliente` DISABLE KEYS */;
INSERT INTO `cliente` (`id_cliente`, `razon_social`) VALUES (1,'Ñandú; \\'S.A.\\' -- /* no es un comentario */');
INSERT INTO `cliente` (`id_cliente`, `razon_social`) VALUES (2,'Segunda\\nlínea');
/*!40000 ALTER TABLE `cliente` ENABLE KEYS */;

DROP TABLE IF EXISTS `tarea`;
CREATE TABLE `tarea` (
  `id_tarea` int NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (`id_tarea`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;

-- Dump completed on 2026-11-02 11:32:50
""".replace("LOCK_PLACEHOLDER", "")

FILAS_BASE = {"cliente": 2, "tarea": 0}


class RegistroMemoria:
    """Historial en memoria con la misma interfaz que RegistroMySQL."""

    tolerante = False

    def __init__(self):
        self.filas = {}
        self._siguiente = 0

    def iniciar(self, operacion, tipo, id_usuario=None, id_relacionado=None):
        self._siguiente += 1
        self.filas[self._siguiente] = {
            "id_respaldo": self._siguiente, "operacion": operacion, "tipo": tipo, "estado": r.ESTADO_EN_CURSO,
            "id_usuario": id_usuario, "id_relacionado": id_relacionado, "nombre_archivo": None,
            "tamano_bytes": None, "sha256": None, "detalle": None, "mensaje_error": None,
            "archivo_eliminado_en": None, "duracion_segundos": None,
        }
        return self._siguiente

    def finalizar(self, id_respaldo, estado, duracion, nombre_archivo=None, tamano_bytes=None,
                  sha256=None, detalle=None, mensaje_error=None):
        self.filas[id_respaldo].update(
            estado=estado, duracion_segundos=duracion, nombre_archivo=nombre_archivo,
            tamano_bytes=tamano_bytes, sha256=sha256, detalle=detalle, mensaje_error=mensaje_error)

    def obtener(self, id_respaldo):
        fila = self.filas.get(id_respaldo)
        return dict(fila) if fila else None

    def listar(self, limite):
        return [dict(f) for f in sorted(self.filas.values(), key=lambda f: -f["id_respaldo"])[:limite]]

    def ultimo_exitoso(self, operacion=r.OPERACION_RESPALDO):
        exitosos = [f for f in self.filas.values() if f["operacion"] == operacion and f["estado"] == r.ESTADO_EXITOSO]
        return dict(max(exitosos, key=lambda f: f["id_respaldo"])) if exitosos else None

    def hay_en_curso(self):
        return any(f["estado"] == r.ESTADO_EN_CURSO for f in self.filas.values())

    def cerrar_huerfanos(self):
        for fila in self.filas.values():
            if fila["estado"] == r.ESTADO_EN_CURSO:
                fila["estado"] = r.ESTADO_FALLIDO
                fila["mensaje_error"] = "Interrumpido"

    def sobrantes(self, conservar):
        vigentes = [f for f in self.filas.values()
                    if f["operacion"] == r.OPERACION_RESPALDO and f["estado"] == r.ESTADO_EXITOSO
                    and f["archivo_eliminado_en"] is None and f["nombre_archivo"]]
        vigentes.sort(key=lambda f: -f["id_respaldo"])
        return [dict(f) for f in reversed(vigentes[conservar:])]

    def marcar_archivo_eliminado(self, id_respaldo):
        self.filas[id_respaldo]["archivo_eliminado_en"] = "ahora"


def volcar_falso(config, ruta_sql):
    with open(ruta_sql, "w", encoding="utf-8") as archivo:
        archivo.write(VOLCADO_BASE)


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    almacen = tmp_path / "almacen"
    adjuntos = tmp_path / "adjuntos"
    adjuntos.mkdir()
    env = {
        "RESPALDO_DIR": str(almacen), "ADJUNTOS_DIR": str(adjuntos), "DB_HOST": "127.0.0.1", "DB_PORT": "3306",
        "DB_NAME": "base_ficticia", "DB_USER": "usuario_ficticio", "DB_PASSWORD": CLAVE_SECRETA,
    }
    monkeypatch.setattr(r, "_volcar_base", volcar_falso)
    monkeypatch.setattr(r, "_migraciones_aplicadas", lambda: ["001", "002"])
    return SimpleNamespace(env=env, config=r.ConfigRespaldo(env), almacen=almacen, adjuntos=adjuntos,
                           registro=RegistroMemoria(), tmp=tmp_path)


def respaldar(entorno, tipo=r.TIPO_MANUAL, usuario=7):
    return r.ejecutar_respaldo(tipo, usuario, config=entorno.config, registro=entorno.registro)


def sha(datos):
    return hashlib.sha256(datos).hexdigest()


# ---------------------------------------------------------------------------
# Construcción de paquetes a mano (válidos y manipulados)
# ---------------------------------------------------------------------------

def manifiesto_valido(sql=VOLCADO_BASE, adjuntos=None, cambios=None):
    datos = sql.encode("utf-8")
    adjuntos = adjuntos or {}
    manifiesto = {
        "formato": 1, "aplicacion": "nahan-asesores", "creado_utc": "2026-11-02T00:00:00Z", "tipo": "MANUAL",
        "herramienta": None, "migraciones": ["001"],
        "base_de_datos": {"archivo": "base_de_datos.sql", "sha256": sha(datos), "bytes": len(datos),
                          "tablas": dict(FILAS_BASE), "excluidas": ["respaldo"]},
        "adjuntos": {"cantidad": len(adjuntos), "omitidos": [],
                     "archivos": {n: {"sha256": sha(c), "bytes": len(c)} for n, c in adjuntos.items()}},
    }
    manifiesto.update(cambios or {})
    return manifiesto


def construir_zip(ruta, sql=VOLCADO_BASE, adjuntos=None, manifiesto=None, extra=(), omitir=()):
    """Escribe un .zip a mano. `extra` son (ZipInfo|str, bytes) añadidos tal cual."""
    adjuntos = adjuntos or {}
    manifiesto = manifiesto if manifiesto is not None else manifiesto_valido(sql, adjuntos)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
            if "manifest.json" not in omitir:
                zf.writestr("manifest.json", manifiesto if isinstance(manifiesto, str) else json.dumps(manifiesto))
            if "base_de_datos.sql" not in omitir:
                zf.writestr("base_de_datos.sql", sql)
            for nombre, contenido in adjuntos.items():
                zf.writestr("adjuntos/" + nombre, contenido)
            for nombre, contenido in extra:
                zf.writestr(nombre, contenido)
    return str(ruta)


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

def test_configuracion_por_defecto_es_conservadora():
    config = r.ConfigRespaldo({})
    assert config.directorio == ""
    assert config.restauracion_habilitada is False
    assert config.retencion_maxima == r.RETENCION_DEFECTO
    assert config.exigir_dispositivo_separado is False


@pytest.mark.parametrize("valor,esperado", [("1", r.RETENCION_MINIMA), ("0", r.RETENCION_MINIMA), ("-5", r.RETENCION_MINIMA),
                                            ("abc", r.RETENCION_DEFECTO), ("10", 10), ("999999", 3650)])
def test_retencion_se_acota(valor, esperado):
    assert r.ConfigRespaldo({"RESPALDO_RETENCION_MAXIMA": valor}).retencion_maxima == esperado


def test_credenciales_propias_de_respaldo_y_restauracion():
    config = r.ConfigRespaldo({"DB_USER": "app", "DB_PASSWORD": "a", "RESPALDO_DB_USER": "resp", "RESPALDO_DB_PASSWORD": "b",
                               "RESTAURACION_DB_USER": "rest", "RESTAURACION_DB_PASSWORD": "c"})
    assert config.credenciales_respaldo == ("resp", "b")
    assert config.credenciales_restauracion == ("rest", "c")
    por_defecto = r.ConfigRespaldo({"DB_USER": "app", "DB_PASSWORD": "a"})
    assert por_defecto.credenciales_respaldo == ("app", "a")
    assert por_defecto.credenciales_restauracion == ("app", "a")


def test_la_configuracion_no_muestra_contrasenas():
    config = r.ConfigRespaldo({"DB_USER": "app", "DB_PASSWORD": CLAVE_SECRETA, "DB_NAME": "x"})
    assert CLAVE_SECRETA not in repr(config)
    assert CLAVE_SECRETA not in str(config)


def test_el_destino_de_la_restauracion_es_la_base_activa_salvo_que_se_configure():
    assert r.ConfigRespaldo({"DB_NAME": "base"}).restaura_base_activa
    otra = r.ConfigRespaldo({"DB_NAME": "base", "RESTAURACION_DB_NAME": "ensayo"})
    assert otra.restauracion_db_nombre == "ensayo" and not otra.restaura_base_activa


@pytest.mark.parametrize("host,puerto,usuario,clave,base", [
    ("-oProxyCommand=x", 3306, "u", "c", "base"),
    ("host con espacios", 3306, "u", "c", "base"),
    ("127.0.0.1", 0, "u", "c", "base"),
    ("127.0.0.1", 3306, "", "c", "base"),
    ("127.0.0.1", 3306, "u\nuser=root", "c", "base"),
    ("127.0.0.1", 3306, "u", "c\npassword=otra", "base"),
    ("127.0.0.1", 3306, "u", "c", "base; DROP DATABASE x"),
    ("127.0.0.1", 3306, "u", "c", "base`"),
    ("127.0.0.1", 3306, "u", "c", ""),
    ("127.0.0.1", 3306, "u", "c", "a" * 65),
])
def test_valores_de_conexion_peligrosos_se_rechazan(host, puerto, usuario, clave, base):
    with pytest.raises(r.ErrorRespaldo):
        r._validar_conexion(host, puerto, usuario, clave, base)


def test_valores_de_conexion_normales_se_aceptan():
    r._validar_conexion("127.0.0.1", 3306, "nahan_app", "una clave con 'comillas' y \\ barras", "nahan_asesores")
    r._validar_conexion("::1", 3306, "nahan_app", "", "nahan_asesores")


# ---------------------------------------------------------------------------
# Almacenamiento seguro y separado (CA5)
# ---------------------------------------------------------------------------

def niveles(evaluacion):
    return {v["clave"]: v["nivel"] for v in evaluacion["verificaciones"]}


def test_sin_directorio_configurado_no_hay_donde_respaldar():
    evaluacion = r.evaluar_almacenamiento(r.ConfigRespaldo({}))
    assert not evaluacion["apto"] and niveles(evaluacion)["configurado"] == "error"
    with pytest.raises(r.AlmacenamientoNoValido):
        r.preparar_almacenamiento(r.ConfigRespaldo({}))


def test_el_directorio_debe_ser_absoluto():
    evaluacion = r.evaluar_almacenamiento(r.ConfigRespaldo({"RESPALDO_DIR": "respaldos/relativo"}))
    assert not evaluacion["apto"] and niveles(evaluacion)["absoluta"] == "error"


@pytest.mark.parametrize("ruta", [
    os.path.join(r.RAIZ_PROYECTO, "respaldos"),
    os.path.join(r.RAIZ_PROYECTO, "frontend", "publico"),
    r.RAIZ_PROYECTO,
    os.path.join(r.RAIZ_PROYECTO, "..", os.path.basename(r.RAIZ_PROYECTO), "uploads"),
])
def test_no_se_acepta_un_directorio_dentro_del_proyecto(ruta):
    evaluacion = r.evaluar_almacenamiento(r.ConfigRespaldo({"RESPALDO_DIR": os.path.abspath(ruta)}), crear=True)
    assert not evaluacion["apto"] and niveles(evaluacion)["ubicacion"] == "error"
    assert not os.path.exists(os.path.join(r.RAIZ_PROYECTO, "respaldos"))


def test_no_se_acepta_un_directorio_dentro_ni_alrededor_de_los_adjuntos(entorno):
    for ruta in (entorno.adjuntos / "respaldos", entorno.tmp):
        config = r.ConfigRespaldo({**entorno.env, "RESPALDO_DIR": str(ruta)})
        assert niveles(r.evaluar_almacenamiento(config))["ubicacion"] == "error"


def test_la_raiz_del_sistema_no_es_un_destino():
    assert not r.evaluar_almacenamiento(r.ConfigRespaldo({"RESPALDO_DIR": os.path.abspath(os.sep)}))["apto"]


def test_la_carpeta_inexistente_sin_directorio_superior_no_es_apta(entorno):
    sin_padre = r.ConfigRespaldo({**entorno.env, "RESPALDO_DIR": str(entorno.tmp / "volumen_sin_montar" / "respaldos")})
    evaluacion = r.evaluar_almacenamiento(sin_padre)
    assert evaluacion["apto"] is False and niveles(evaluacion)["existe"] == "error"
    assert not (entorno.tmp / "volumen_sin_montar").exists(), "evaluar no crea nada"


def test_se_crea_solo_el_ultimo_nivel_y_con_permisos_0700(entorno):
    r.preparar_almacenamiento(entorno.config)
    assert stat.S_IMODE(os.stat(entorno.almacen).st_mode) == 0o700

    sin_padre = r.ConfigRespaldo({**entorno.env, "RESPALDO_DIR": str(entorno.tmp / "no_existe" / "respaldos")})
    evaluacion = r.evaluar_almacenamiento(sin_padre, crear=True)
    assert not evaluacion["apto"] and niveles(evaluacion)["existe"] == "error"
    assert "montado" in evaluacion["verificaciones"][-1]["mensaje"]
    assert not (entorno.tmp / "no_existe").exists()


@pytest.mark.skipif(os.name != "posix", reason="permisos POSIX")
def test_un_directorio_demasiado_abierto_se_corrige_a_0700(entorno):
    os.mkdir(entorno.almacen, 0o755)
    os.chmod(entorno.almacen, 0o755)
    evaluacion = r.evaluar_almacenamiento(entorno.config, crear=True)
    assert niveles(evaluacion)["permisos"] == "ok"
    assert stat.S_IMODE(os.stat(entorno.almacen).st_mode) == 0o700


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="requiere un usuario sin privilegios")
def test_un_directorio_sin_permiso_de_escritura_se_informa(entorno):
    os.mkdir(entorno.almacen, 0o700)
    os.chmod(entorno.almacen, 0o500)
    try:
        evaluacion = r.evaluar_almacenamiento(entorno.config, crear=True)
        assert not evaluacion["apto"] and niveles(evaluacion)["escritura"] == "error"
    finally:
        os.chmod(entorno.almacen, 0o700)


def test_la_independencia_del_dispositivo_se_informa_sin_afirmar_de_mas(entorno, monkeypatch):
    monkeypatch.setattr(r, "_dispositivo_distinto", lambda ruta: False)
    mismo = r.evaluar_almacenamiento(entorno.config, crear=True)
    assert mismo["apto"] and mismo["independiente"] is False
    assert niveles(mismo)["independencia"] == "aviso"

    monkeypatch.setattr(r, "_dispositivo_distinto", lambda ruta: True)
    otro = r.evaluar_almacenamiento(entorno.config, crear=True)
    assert otro["independiente"] is True and niveles(otro)["independencia"] == "ok"


def test_exigir_dispositivo_separado_impide_respaldar_en_el_mismo_disco(entorno, monkeypatch):
    monkeypatch.setattr(r, "_dispositivo_distinto", lambda ruta: False)
    config = r.ConfigRespaldo({**entorno.env, "RESPALDO_EXIGIR_DISPOSITIVO_SEPARADO": "true"})
    with pytest.raises(r.AlmacenamientoNoValido, match="mismo dispositivo"):
        r.ejecutar_respaldo(r.TIPO_MANUAL, 1, config=config, registro=entorno.registro)
    assert [f["estado"] for f in entorno.registro.filas.values()] == [r.ESTADO_FALLIDO]
    assert list(entorno.almacen.glob("*.zip")) == []


def test_poco_espacio_libre_es_un_error(entorno, monkeypatch):
    monkeypatch.setattr(r.shutil, "disk_usage", lambda ruta: SimpleNamespace(free=1024))
    evaluacion = r.evaluar_almacenamiento(entorno.config, crear=True)
    assert not evaluacion["apto"] and niveles(evaluacion)["espacio"] == "error"


# ---------------------------------------------------------------------------
# Respaldo: archivo generado, historial y errores (CA2, CA3)
# ---------------------------------------------------------------------------

def test_respaldo_manual_genera_el_paquete_y_lo_registra(entorno):
    resultado = respaldar(entorno)
    ruta = entorno.almacen / resultado["nombre_archivo"]
    assert r.PATRON_NOMBRE_PAQUETE.match(ruta.name)
    assert ruta.stat().st_size == resultado["tamano_bytes"] > 0
    assert sha(ruta.read_bytes()) == resultado["sha256"]
    assert (entorno.almacen / (ruta.name + ".sha256")).read_text().split()[0] == resultado["sha256"]

    fila = entorno.registro.obtener(resultado["id_respaldo"])
    assert fila["estado"] == "EXITOSO" and fila["tipo"] == "MANUAL" and fila["operacion"] == "RESPALDO"
    assert fila["id_usuario"] == 7 and fila["nombre_archivo"] == ruta.name
    assert fila["duracion_segundos"] is not None and fila["mensaje_error"] is None
    assert "tablas=2" in fila["detalle"] and "filas=2" in fila["detalle"]


@pytest.mark.skipif(os.name != "posix", reason="permisos POSIX")
def test_el_paquete_queda_legible_solo_para_el_propietario(entorno):
    resultado = respaldar(entorno)
    for nombre in (resultado["nombre_archivo"], resultado["nombre_archivo"] + ".sha256"):
        assert stat.S_IMODE(os.stat(entorno.almacen / nombre).st_mode) == 0o600


def test_el_paquete_contiene_manifiesto_base_y_adjuntos(entorno):
    (entorno.adjuntos / "a1b2c3.pdf").write_bytes(b"%PDF ficticio")
    (entorno.adjuntos / "sub").mkdir()
    (entorno.adjuntos / "sub" / "x.png").write_bytes(b"png ficticio")
    resultado = respaldar(entorno)
    with zipfile.ZipFile(entorno.almacen / resultado["nombre_archivo"]) as zf:
        assert sorted(zf.namelist()) == ["adjuntos/a1b2c3.pdf", "adjuntos/sub/x.png", "base_de_datos.sql", "manifest.json"]
        manifiesto = json.loads(zf.read("manifest.json"))
        assert zf.read("adjuntos/a1b2c3.pdf") == b"%PDF ficticio"
    assert manifiesto["formato"] == 1 and manifiesto["aplicacion"] == "nahan-asesores"
    assert manifiesto["migraciones"] == ["001", "002"]
    assert manifiesto["base_de_datos"]["tablas"] == FILAS_BASE
    assert manifiesto["base_de_datos"]["excluidas"] == ["respaldo", "intento_login_fallido"]
    assert set(manifiesto["adjuntos"]["archivos"]) == {"a1b2c3.pdf", "sub/x.png"}
    assert manifiesto["adjuntos"]["archivos"]["a1b2c3.pdf"]["sha256"] == sha(b"%PDF ficticio")


def test_los_adjuntos_no_seguros_se_omiten_y_se_informan(entorno):
    (entorno.adjuntos / "bueno.pdf").write_bytes(b"ok")
    (entorno.adjuntos / ".oculto").write_bytes(b"x")
    (entorno.adjuntos / "con espacio.pdf").write_bytes(b"x")
    afuera = entorno.tmp / "secreto.txt"
    afuera.write_text("no debe respaldarse")
    os.symlink(afuera, entorno.adjuntos / "enlace.txt")
    os.symlink(entorno.tmp, entorno.adjuntos / "carpeta_enlace")

    resultado = respaldar(entorno)
    manifiesto = resultado["manifiesto"]
    assert list(manifiesto["adjuntos"]["archivos"]) == ["bueno.pdf"]
    assert {"enlace.txt", ".oculto", "con espacio.pdf"} <= set(manifiesto["adjuntos"]["omitidos"])
    assert "adjuntos_omitidos" in entorno.registro.obtener(resultado["id_respaldo"])["detalle"]
    with zipfile.ZipFile(entorno.almacen / resultado["nombre_archivo"]) as zf:
        assert all("secreto" not in zf.read(n).decode("latin-1", "ignore") for n in zf.namelist() if n.startswith("adjuntos/"))


def test_sin_directorio_de_adjuntos_el_respaldo_sigue_siendo_valido(entorno):
    entorno.adjuntos.rmdir()
    resultado = respaldar(entorno)
    assert resultado["manifiesto"]["adjuntos"]["cantidad"] == 0


def test_respaldo_programado_se_registra_sin_usuario(entorno):
    resultado = r.ejecutar_respaldo(r.TIPO_PROGRAMADO, config=entorno.config, registro=entorno.registro)
    fila = entorno.registro.obtener(resultado["id_respaldo"])
    assert fila["tipo"] == "PROGRAMADO" and fila["id_usuario"] is None and fila["estado"] == "EXITOSO"


@pytest.mark.parametrize("tipo", ["PREVIO_RESTAURACION", "OTRO", "", None, "manual"])
def test_solo_se_pueden_pedir_respaldos_manuales_o_programados(entorno, tipo):
    with pytest.raises(r.ErrorRespaldo):
        r.ejecutar_respaldo(tipo, 1, config=entorno.config, registro=entorno.registro)
    assert entorno.registro.filas == {}


def test_un_fallo_del_volcado_queda_registrado_y_no_deja_restos(entorno, monkeypatch):
    def falla(config, ruta_sql):
        with open(ruta_sql, "w") as archivo:
            archivo.write("-- volcado a medias\n")
        raise r.ErrorRespaldo("mysqldump falló (código 2): Access denied")
    monkeypatch.setattr(r, "_volcar_base", falla)

    with pytest.raises(r.ErrorRespaldo, match="Access denied") as info:
        respaldar(entorno)
    fila = entorno.registro.obtener(info.value.id_respaldo)
    assert fila["estado"] == "FALLIDO" and "Access denied" in fila["mensaje_error"]
    assert fila["nombre_archivo"] is None and fila["sha256"] is None
    assert sorted(p.name for p in entorno.almacen.iterdir()) == [".operacion.lock"]


def test_un_error_inesperado_no_filtra_detalles_internos(entorno, monkeypatch):
    def explota(config, ruta_sql):
        raise RuntimeError(f"fallo interno con {CLAVE_SECRETA} y /ruta/privada")
    monkeypatch.setattr(r, "_volcar_base", explota)

    with pytest.raises(r.ErrorRespaldo) as info:
        respaldar(entorno)
    fila = entorno.registro.obtener(info.value.id_respaldo)
    for texto in (str(info.value), fila["mensaje_error"]):
        assert CLAVE_SECRETA not in texto and "/ruta/privada" not in texto
    assert fila["estado"] == "FALLIDO"


def test_un_almacenamiento_invalido_deja_el_intento_en_el_historial(entorno):
    config = r.ConfigRespaldo({**entorno.env, "RESPALDO_DIR": ""})
    with pytest.raises(r.AlmacenamientoNoValido) as info:
        r.ejecutar_respaldo(r.TIPO_PROGRAMADO, config=config, registro=entorno.registro)
    fila = entorno.registro.obtener(info.value.id_respaldo)
    assert fila["estado"] == "FALLIDO" and "RESPALDO_DIR" in fila["mensaje_error"]


def test_un_volcado_con_sentencias_no_soportadas_hace_fallar_el_respaldo(entorno, monkeypatch):
    def con_trigger(config, ruta_sql):
        with open(ruta_sql, "w") as archivo:
            archivo.write(VOLCADO_BASE.replace("-- Dump completed", "DELIMITER ;;\nCREATE TRIGGER t BEFORE INSERT ON x FOR EACH ROW BEGIN END;;\n-- Dump completed"))
    monkeypatch.setattr(r, "_volcar_base", con_trigger)
    with pytest.raises(r.RespaldoNoValido, match="no admitida"):
        respaldar(entorno)
    assert list(entorno.almacen.glob("*.zip")) == []


def test_un_volcado_incompleto_hace_fallar_el_respaldo(entorno, monkeypatch):
    def truncado(config, ruta_sql):
        with open(ruta_sql, "w") as archivo:
            archivo.write(VOLCADO_BASE.replace("-- Dump completed on 2026-11-02 11:32:50\n", ""))
    monkeypatch.setattr(r, "_volcar_base", truncado)
    with pytest.raises(r.RespaldoNoValido, match="incompleto"):
        respaldar(entorno)


# ---------------------------------------------------------------------------
# Concurrencia
# ---------------------------------------------------------------------------

def test_no_se_permiten_dos_operaciones_a_la_vez(entorno):
    existente = respaldar(entorno)
    filas_antes = dict(entorno.registro.filas)
    habilitada = r.ConfigRespaldo({**entorno.env, "RESTAURACION_HABILITADA": "true"})
    with r._Bloqueo(str(entorno.almacen / ".operacion.lock")):
        with pytest.raises(r.OperacionEnCurso):
            respaldar(entorno)
        with pytest.raises(r.OperacionEnCurso):
            r.ejecutar_restauracion(existente["id_respaldo"], 1, config=habilitada, registro=entorno.registro)
    assert entorno.registro.filas == filas_antes, "el intento rechazado no deja filas en el historial"
    respaldar(entorno)


def test_el_bloqueo_se_libera_aunque_el_respaldo_falle(entorno, monkeypatch):
    original = r._volcar_base
    monkeypatch.setattr(r, "_volcar_base", lambda c, p: (_ for _ in ()).throw(r.ErrorRespaldo("falla")))
    with pytest.raises(r.ErrorRespaldo):
        respaldar(entorno)
    monkeypatch.setattr(r, "_volcar_base", original)
    respaldar(entorno)


def test_dos_respaldos_simultaneos_en_hilos_solo_dejan_pasar_uno(entorno, monkeypatch):
    dentro, soltar = threading.Event(), threading.Event()
    original = r._volcar_base

    def lento(config, ruta_sql):
        dentro.set()
        assert soltar.wait(10)
        original(config, ruta_sql)
    monkeypatch.setattr(r, "_volcar_base", lento)

    resultados = []
    hilo = threading.Thread(target=lambda: resultados.append(respaldar(entorno)))
    hilo.start()
    assert dentro.wait(10)
    try:
        with pytest.raises(r.OperacionEnCurso):
            respaldar(entorno)
        assert entorno.registro.hay_en_curso()
    finally:
        soltar.set()
        hilo.join(20)
    assert len(resultados) == 1
    assert [f["estado"] for f in entorno.registro.filas.values()] == ["EXITOSO"]


def test_las_operaciones_huerfanas_se_cierran_como_fallidas(entorno):
    huerfana = entorno.registro.iniciar("RESPALDO", "PROGRAMADO")
    (entorno.almacen).mkdir(mode=0o700)
    (entorno.almacen / ".parcial-abc.zip").write_bytes(b"resto")
    (entorno.almacen / ".trabajo-xyz").mkdir()
    respaldar(entorno)
    assert entorno.registro.obtener(huerfana)["estado"] == "FALLIDO"
    assert "Interrumpido" in entorno.registro.obtener(huerfana)["mensaje_error"]
    assert not any(p.name.startswith((".parcial-", ".trabajo-")) for p in entorno.almacen.iterdir())


def test_el_marcador_de_mantenimiento_solo_vale_con_el_bloqueo_tomado(entorno, monkeypatch):
    monkeypatch.setenv("RESPALDO_DIR", str(entorno.almacen))
    assert r.restauracion_en_curso() is False

    r.preparar_almacenamiento(entorno.config)
    marcador = entorno.almacen / r.ARCHIVO_MANTENIMIENTO
    marcador.write_text("{}")
    assert r.restauracion_en_curso() is False, "un marcador huérfano (proceso muerto) no debe bloquear la aplicación"

    with r._Bloqueo(str(entorno.almacen / r.ARCHIVO_BLOQUEO)):
        assert r.restauracion_en_curso() is True
    assert r.restauracion_en_curso() is False

    monkeypatch.delenv("RESPALDO_DIR")
    assert r.restauracion_en_curso() is False


def test_el_modo_mantenimiento_deja_y_retira_el_marcador(entorno):
    r.preparar_almacenamiento(entorno.config)
    marcador = entorno.almacen / r.ARCHIVO_MANTENIMIENTO
    with pytest.raises(ValueError):
        with r._modo_mantenimiento(str(entorno.almacen)):
            assert marcador.exists()
            raise ValueError
    assert not marcador.exists()


# ---------------------------------------------------------------------------
# Retención
# ---------------------------------------------------------------------------

def test_la_retencion_elimina_los_paquetes_mas_antiguos(entorno, monkeypatch):
    config = r.ConfigRespaldo({**entorno.env, "RESPALDO_RETENCION_MAXIMA": "3"})
    entorno.config = config
    resultados = []
    for _ in range(5):
        resultados.append(respaldar(entorno))
        time.sleep(0.01)

    paquetes = sorted(p.name for p in entorno.almacen.glob("*.zip"))
    assert paquetes == sorted(x["nombre_archivo"] for x in resultados[-3:])
    assert sorted(p.name for p in entorno.almacen.glob("*.sha256")) == [n + ".sha256" for n in paquetes]
    eliminados = [i for i, f in entorno.registro.filas.items() if f["archivo_eliminado_en"]]
    assert eliminados == [resultados[0]["id_respaldo"], resultados[1]["id_respaldo"]]
    assert all(f["estado"] == "EXITOSO" for f in entorno.registro.filas.values()), "el historial se conserva"


def test_la_retencion_ignora_nombres_ajenos(entorno):
    r.preparar_almacenamiento(entorno.config)
    ajeno = entorno.almacen / "notas.txt"
    ajeno.write_text("no tocar")
    entorno.registro.filas[1] = {"id_respaldo": 1, "operacion": "RESPALDO", "estado": "EXITOSO", "nombre_archivo": "../notas.txt",
                                 "archivo_eliminado_en": None}
    r._aplicar_retencion(r.ConfigRespaldo({**entorno.env, "RESPALDO_RETENCION_MAXIMA": "3"}), entorno.registro, str(entorno.almacen))
    assert ajeno.exists()


# ---------------------------------------------------------------------------
# Herramientas externas: sin shell y sin secretos en argumentos
# ---------------------------------------------------------------------------

class SubprocesoFalso:
    def __init__(self, codigo=0, stderr=b"", volcado=VOLCADO_BASE):
        self.llamadas = []
        self.opciones_durante = None
        self.permisos_durante = None
        self.codigo, self.stderr, self.volcado = codigo, stderr, volcado

    def __call__(self, argumentos, **kwargs):
        self.llamadas.append((argumentos, kwargs))
        opciones = argumentos[1].split("=", 1)[1]
        with open(opciones, encoding="utf-8") as archivo:
            self.opciones_durante = archivo.read()
        self.permisos_durante = stat.S_IMODE(os.stat(opciones).st_mode)
        self.ruta_opciones = opciones
        kwargs["stdout"].write(self.volcado.encode("utf-8"))
        return subprocess.CompletedProcess(argumentos, self.codigo, b"", self.stderr)


def test_mysqldump_se_llama_sin_shell_ni_contrasena_en_los_argumentos(entorno, monkeypatch, tmp_path):
    monkeypatch.undo()
    falso = SubprocesoFalso()
    monkeypatch.setattr(r.subprocess, "run", falso)
    config = r.ConfigRespaldo({**entorno.env, "DB_PASSWORD": 'clave "con" comillas \\ y barra'})
    destino = tmp_path / "salida.sql"

    r._volcar_base(config, str(destino))

    argumentos, kwargs = falso.llamadas[0]
    assert isinstance(argumentos, list) and not kwargs.get("shell")
    assert argumentos[0] == "mysqldump" and argumentos[1].startswith("--defaults-file=")
    assert not any("clave" in a or "comillas" in a for a in argumentos)
    assert "--single-transaction" in argumentos and "--ignore-table=base_ficticia.respaldo" in argumentos
    assert "--ignore-table=base_ficticia.intento_login_fallido" in argumentos
    assert argumentos[-1] == "base_ficticia"
    assert kwargs["stdin"] == subprocess.DEVNULL and kwargs["timeout"] == config.timeout
    assert set(kwargs["env"]) <= {"PATH", "SYSTEMROOT", "TEMP", "TMP", "LANG", "LC_ALL"}
    assert 'password="clave \\"con\\" comillas \\\\ y barra"' in falso.opciones_durante
    assert 'user="usuario_ficticio"' in falso.opciones_durante
    if os.name == "posix":
        assert falso.permisos_durante == 0o600
    assert not os.path.exists(falso.ruta_opciones), "el archivo de opciones se borra al terminar"
    assert destino.read_text() == VOLCADO_BASE


def test_un_mysqldump_con_error_no_filtra_credenciales(entorno, monkeypatch, tmp_path):
    monkeypatch.undo()
    stderr = b"mysqldump: [Warning] Using a password on the command line interface can be insecure.\nmysqldump: Got error: 1045: Access denied for user 'x'@'localhost' (using password: YES) when trying to connect\n"
    monkeypatch.setattr(r.subprocess, "run", SubprocesoFalso(codigo=2, stderr=stderr))
    with pytest.raises(r.ErrorRespaldo) as info:
        r._volcar_base(entorno.config, str(tmp_path / "x.sql"))
    assert "código 2" in info.value.mensaje and "Access denied" in info.value.mensaje
    assert "Using a password" not in info.value.mensaje and CLAVE_SECRETA not in info.value.mensaje


def test_mysqldump_inexistente_o_lento_se_informa(entorno, monkeypatch, tmp_path):
    monkeypatch.undo()

    def no_existe(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(r.subprocess, "run", no_existe)
    with pytest.raises(r.ErrorRespaldo, match="MYSQLDUMP_BIN"):
        r._volcar_base(entorno.config, str(tmp_path / "x.sql"))

    def lento(*a, **k):
        raise subprocess.TimeoutExpired("mysqldump", 1)
    monkeypatch.setattr(r.subprocess, "run", lento)
    with pytest.raises(r.ErrorRespaldo, match="tiempo máximo"):
        r._volcar_base(entorno.config, str(tmp_path / "x.sql"))


# ---------------------------------------------------------------------------
# Lectura del volcado
# ---------------------------------------------------------------------------

def escribir(tmp_path, texto, nombre="v.sql"):
    ruta = tmp_path / nombre
    ruta.write_text(texto, encoding="utf-8")
    return str(ruta)


def test_el_volcado_real_se_reconoce_y_se_cuentan_las_filas(tmp_path):
    ruta = escribir(tmp_path, VOLCADO_BASE)
    tipos = [t for t, _, _ in r.sentencias_del_volcado(ruta)]
    assert tipos.count("INSERT") == 2 and tipos.count("CREATE") == 2 and tipos.count("DROP") == 2
    assert r.resumir_volcado(ruta) == FILAS_BASE


@pytest.mark.parametrize("peligrosa", [
    "\\! touch /tmp/pwned",
    "system id",
    "source /etc/passwd",
    "\\. /etc/passwd",
    "GRANT ALL PRIVILEGES ON *.* TO 'x'@'%';",
    "CREATE USER 'x'@'%' IDENTIFIED BY 'y';",
    "DROP DATABASE base_ficticia;",
    "USE mysql;",
    "UPDATE usuario SET id_rol = 1;",
    "DELETE FROM auditoria;",
    "DROP TABLE `cliente`;",
    "SET GLOBAL local_infile = 1;",
    "DELIMITER ;;",
    "CREATE DEFINER=`root`@`%` TRIGGER t BEFORE INSERT ON cliente FOR EACH ROW SET NEW.x = 1;",
    "INSERT INTO cliente VALUES (1,'x');",
    "INSERT INTO `cliente` (`id_cliente`) VALUES (1); DROP TABLE `usuario`;--",
    "SELECT SLEEP(100);",
    "/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER t BEFORE INSERT ON x FOR EACH ROW BEGIN END */;",
    "/*!40101 DROP TABLE `usuario` */;",
])
def test_el_volcado_rechaza_sentencias_que_no_genera_mysqldump(tmp_path, peligrosa):
    texto = VOLCADO_BASE.replace("-- Dump completed", peligrosa + "\n-- Dump completed")
    with pytest.raises(r.RespaldoNoValido):
        r.resumir_volcado(escribir(tmp_path, texto))


def test_el_volcado_rechaza_contenido_tras_el_fin_y_create_sin_cerrar(tmp_path):
    with pytest.raises(r.RespaldoNoValido, match="después del fin"):
        r.resumir_volcado(escribir(tmp_path, VOLCADO_BASE + "DROP TABLE IF EXISTS `x`;\n"))
    sin_cerrar = VOLCADO_BASE.replace(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n/*!40101 SET SQL_MODE", "/*!40101 SET SQL_MODE")
    with pytest.raises(r.RespaldoNoValido):
        r.resumir_volcado(escribir(tmp_path, sin_cerrar, "b.sql"))


def test_un_volcado_sin_tablas_no_es_un_respaldo(tmp_path):
    vacio = "-- MySQL dump\n/*!40101 SET NAMES utf8mb4 */;\n-- Dump completed on x\n"
    with pytest.raises(r.RespaldoNoValido, match="ninguna tabla"):
        r.resumir_volcado(escribir(tmp_path, vacio))


# ---------------------------------------------------------------------------
# Validación del paquete: archivos manipulados y rutas inseguras
# ---------------------------------------------------------------------------

def abrir(entorno, ruta, **kwargs):
    return r.abrir_paquete(str(ruta), entorno.config, **kwargs)


def test_un_paquete_bien_formado_se_valida_y_se_extrae(entorno, tmp_path):
    ruta = construir_zip(tmp_path / "p.zip", adjuntos={"a.pdf": b"contenido", "dir/b.txt": b"otro"})
    destino = tmp_path / "salida"
    destino.mkdir()
    manifiesto = abrir(entorno, ruta, sha256_esperado=sha(open(ruta, "rb").read()), extraer_en=str(destino))
    assert manifiesto["base_de_datos"]["tablas"] == FILAS_BASE
    assert (destino / "base_de_datos.sql").read_text() == VOLCADO_BASE
    assert (destino / "adjuntos" / "a.pdf").read_bytes() == b"contenido"
    assert (destino / "adjuntos" / "dir" / "b.txt").read_bytes() == b"otro"
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".trabajo-")]


def info_symlink(nombre, destino="/etc/passwd"):
    info = zipfile.ZipInfo(nombre)
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    return info, destino.encode()


@pytest.mark.parametrize("nombre", [
    "../evil.txt", "/etc/passwd", "adjuntos/../../evil.txt", "adjuntos/../evil", "adjuntos//x.pdf", "adjuntos/./x.pdf",
    "adjuntos\\x.pdf", "adjuntos/C:/x.pdf", "adjuntos/con espacio.pdf", "adjuntos/.oculto", "adjuntos/\x00.pdf",
    "otro/archivo.txt", "adjuntos/" + "a" * 300, "base_de_datos.sql.bak", "MANIFEST.JSON",
])
def test_se_rechazan_miembros_con_rutas_inseguras(entorno, tmp_path, nombre):
    ruta = construir_zip(tmp_path / "p.zip", extra=[(nombre, b"x")])
    with pytest.raises(r.RespaldoNoValido):
        abrir(entorno, ruta)
    assert not (tmp_path.parent / "evil.txt").exists()


@pytest.mark.parametrize("nombre,valido", [
    ("manifest.json", True), ("base_de_datos.sql", True), ("adjuntos/a1b2.pdf", True), ("adjuntos/sub/x.png", True),
    ("../manifest.json", False), ("/manifest.json", False), ("adjuntos/../x", False), ("adjuntos/", False),
    ("adjuntos", False), ("adjuntos\\x", False), ("adjuntos/.x", False), ("adjuntos/a b", False), ("x/manifest.json", False),
    ("adjuntos/\x00", False), ("adjuntos/ñ.pdf", False), ("", False),
])
def test_la_primera_defensa_de_nombres_de_miembros_funciona_por_si_sola(nombre, valido):
    assert r._nombre_miembro_valido(nombre) is valido


def test_se_rechazan_enlaces_simbolicos_directorios_y_cifrado(entorno, tmp_path):
    enlace = construir_zip(tmp_path / "enlace.zip", extra=[info_symlink("adjuntos/enlace.txt")])
    with pytest.raises(r.RespaldoNoValido):
        abrir(entorno, enlace)

    directorio = construir_zip(tmp_path / "dir.zip", extra=[("adjuntos/", b"")])
    with pytest.raises(r.RespaldoNoValido):
        abrir(entorno, directorio)

    cifrado = tmp_path / "cifrado.zip"
    construir_zip(cifrado)
    datos = bytearray(cifrado.read_bytes())
    for indice in range(len(datos) - 4):
        if datos[indice:indice + 4] == b"PK\x01\x02":
            datos[indice + 8] |= 0x01  # bandera de cifrado en la cabecera central
    cifrado.write_bytes(bytes(datos))
    with pytest.raises(r.RespaldoNoValido):
        abrir(entorno, cifrado)


def test_se_rechazan_miembros_duplicados_faltantes_y_sobrantes(entorno, tmp_path):
    with pytest.raises(r.RespaldoNoValido):
        abrir(entorno, construir_zip(tmp_path / "dup.zip", extra=[("base_de_datos.sql", VOLCADO_BASE)]))
    with pytest.raises(r.RespaldoNoValido, match="faltan"):
        abrir(entorno, construir_zip(tmp_path / "sinman.zip", omitir=("manifest.json",)))
    with pytest.raises(r.RespaldoNoValido, match="faltan"):
        abrir(entorno, construir_zip(tmp_path / "sinsql.zip", omitir=("base_de_datos.sql",)))
    with pytest.raises(r.RespaldoNoValido, match="no coincide con el manifiesto"):
        abrir(entorno, construir_zip(tmp_path / "extra.zip", extra=[("adjuntos/sorpresa.exe", b"MZ")]))
    manifiesto = manifiesto_valido(adjuntos={"falta.pdf": b"x"})
    with pytest.raises(r.RespaldoNoValido, match="no coincide con el manifiesto"):
        abrir(entorno, construir_zip(tmp_path / "falta.zip", manifiesto=manifiesto))


def test_se_detecta_contenido_alterado_respecto_del_manifiesto(entorno, tmp_path):
    manifiesto = manifiesto_valido(adjuntos={"a.pdf": b"original"})
    ruta = construir_zip(tmp_path / "a.zip", adjuntos={"a.pdf": b"ALTERADO!"}, manifiesto=manifiesto)
    with pytest.raises(r.RespaldoNoValido, match="a.pdf"):
        abrir(entorno, ruta)

    alterado = VOLCADO_BASE.replace("Segunda", "Cambiad")
    ruta = construir_zip(tmp_path / "b.zip", sql=alterado, manifiesto=manifiesto_valido())
    with pytest.raises(r.RespaldoNoValido, match="base_de_datos.sql"):
        abrir(entorno, ruta)


@pytest.mark.parametrize("cambios", [
    {"formato": 2}, {"formato": "1"}, {"aplicacion": "otra-app"}, {"base_de_datos": {}}, {"adjuntos": []},
    {"migraciones": "001"}, {"migraciones": ["../x"]}, {"migraciones": ["٠٠١"]},
])
def test_se_rechazan_manifiestos_invalidos(entorno, tmp_path, cambios):
    ruta = construir_zip(tmp_path / "m.zip", manifiesto=manifiesto_valido(cambios=cambios))
    with pytest.raises(r.RespaldoNoValido):
        abrir(entorno, ruta)


@pytest.mark.parametrize("modificar", [
    lambda m: m["base_de_datos"].update(sha256="xyz"),
    lambda m: m["base_de_datos"].update(bytes=-1),
    lambda m: m["base_de_datos"].update(tablas={"cliente; DROP": 1}),
    lambda m: m["base_de_datos"].update(tablas={"cliente": -3}),
    lambda m: m["base_de_datos"].update(tablas={}),
    lambda m: m["base_de_datos"].update(archivo="../otro.sql"),
    lambda m: m["adjuntos"]["archivos"].update({"../fuga.txt": {"sha256": "0" * 64, "bytes": 1}}),
    lambda m: m["adjuntos"]["archivos"].update({"a.pdf": {"sha256": "no", "bytes": 1}}),
])
def test_se_rechazan_campos_peligrosos_del_manifiesto(entorno, tmp_path, modificar):
    manifiesto = manifiesto_valido(adjuntos={"a.pdf": b"x"})
    modificar(manifiesto)
    ruta = construir_zip(tmp_path / "m.zip", adjuntos={"a.pdf": b"x"}, manifiesto=manifiesto)
    with pytest.raises(r.RespaldoNoValido):
        abrir(entorno, ruta)


def test_manifiesto_ilegible_o_demasiado_grande(entorno, tmp_path):
    with pytest.raises(r.RespaldoNoValido, match="manifiesto"):
        abrir(entorno, construir_zip(tmp_path / "a.zip", manifiesto="{no es json"))
    with pytest.raises(r.RespaldoNoValido, match="demasiado grande"):
        abrir(entorno, construir_zip(tmp_path / "b.zip", manifiesto=" " * (6 * 1024 * 1024) + "{}"))
    with pytest.raises(r.RespaldoNoValido):
        abrir(entorno, construir_zip(tmp_path / "c.zip", manifiesto="[1, 2]"))


def test_el_volcado_debe_coincidir_con_las_tablas_del_manifiesto(entorno, tmp_path):
    manifiesto = manifiesto_valido()
    manifiesto["base_de_datos"]["tablas"] = {"cliente": 99, "tarea": 0}
    with pytest.raises(r.RespaldoNoValido, match="tablas del volcado"):
        abrir(entorno, construir_zip(tmp_path / "t.zip", manifiesto=manifiesto))


def test_se_rechaza_un_volcado_con_sentencias_ajenas_aunque_el_manifiesto_coincida(entorno, tmp_path):
    maligno = VOLCADO_BASE.replace("-- Dump completed", "GRANT ALL ON *.* TO 'x'@'%';\n-- Dump completed")
    with pytest.raises(r.RespaldoNoValido):
        abrir(entorno, construir_zip(tmp_path / "g.zip", sql=maligno))


def test_se_rechaza_lo_que_no_es_un_paquete(entorno, tmp_path):
    (tmp_path / "vacio.zip").write_bytes(b"")
    (tmp_path / "basura.zip").write_bytes(os.urandom(500))
    (tmp_path / "texto.zip").write_text("no soy un zip")
    for nombre in ("vacio.zip", "basura.zip", "texto.zip"):
        with pytest.raises(r.RespaldoNoValido):
            abrir(entorno, tmp_path / nombre)
    with pytest.raises(r.RespaldoNoEncontrado):
        abrir(entorno, tmp_path / "no_existe.zip")
    with pytest.raises(r.RespaldoNoValido):
        abrir(entorno, tmp_path)


def test_un_paquete_truncado_o_con_bits_alterados_se_rechaza(entorno, tmp_path):
    ruta = tmp_path / "p.zip"
    construir_zip(ruta, adjuntos={"a.pdf": os.urandom(4000)})
    datos = ruta.read_bytes()
    (tmp_path / "truncado.zip").write_bytes(datos[: len(datos) // 2])
    with pytest.raises(r.RespaldoNoValido):
        abrir(entorno, tmp_path / "truncado.zip")

    corrupto = bytearray(datos)
    corrupto[60] ^= 0xFF  # dentro de los datos comprimidos del primer miembro
    (tmp_path / "corrupto.zip").write_bytes(bytes(corrupto))
    with pytest.raises(r.RespaldoNoValido):
        abrir(entorno, tmp_path / "corrupto.zip")


def test_la_huella_del_paquete_debe_coincidir_con_la_registrada(entorno, tmp_path):
    ruta = construir_zip(tmp_path / "p.zip")
    huella = sha(open(ruta, "rb").read())
    abrir(entorno, ruta, sha256_esperado=huella)
    with pytest.raises(r.RespaldoNoValido, match="SHA-256"):
        abrir(entorno, ruta, sha256_esperado="0" * 64)


def test_un_enlace_simbolico_no_se_acepta_como_paquete(entorno, tmp_path):
    real = construir_zip(tmp_path / "real.zip")
    os.symlink(real, tmp_path / "enlace.zip")
    with pytest.raises(r.RespaldoNoValido, match="regular"):
        abrir(entorno, tmp_path / "enlace.zip")


def test_los_limites_de_tamano_se_aplican(entorno, tmp_path):
    ruta = construir_zip(tmp_path / "p.zip", adjuntos={"a.pdf": b"x" * 5000})
    entorno.config.limite_bytes = 1000
    with pytest.raises(r.RespaldoNoValido, match="límite"):
        abrir(entorno, ruta)


@pytest.mark.parametrize("nombre", [
    "../nahan-respaldo-20261102T050000Z-1a2b3c4d.zip", "/etc/passwd", "nahan-respaldo-x.zip", "otro.zip", "",
    "nahan-respaldo-20261102T050000Z-1a2b3c4d.zip/../../x", "nahan-respaldo-20261102T050000Z-1A2B3C4D.zip",
    "nahan-respaldo-20261102T050000Z-1a2b3c4d.zip\n", None, 5, "nahan-respaldo-20261102T050000Z-1a2b3c4d.zip.sha256",
    "nahan-respaldo-٢٠٢٦١١٠٢T050000Z-1a2b3c4d.zip",
])
def test_el_nombre_del_paquete_nunca_se_acepta_si_no_tiene_el_formato_propio(entorno, nombre):
    r.preparar_almacenamiento(entorno.config)
    with pytest.raises(r.RespaldoNoEncontrado):
        r.resolver_paquete(entorno.config, nombre)


def test_un_paquete_enlazado_fuera_del_almacen_no_se_resuelve(entorno):
    r.preparar_almacenamiento(entorno.config)
    afuera = entorno.tmp / "afuera.zip"
    afuera.write_bytes(b"x")
    nombre = "nahan-respaldo-20261102T050000Z-1a2b3c4d.zip"
    os.symlink(afuera, entorno.almacen / nombre)
    with pytest.raises(r.RespaldoNoValido, match="no es segura"):
        r.resolver_paquete(entorno.config, nombre)


# ---------------------------------------------------------------------------
# Restauración: puertas de seguridad previas (el recorrido real está en test_rf60_mysql_real.py)
# ---------------------------------------------------------------------------

def test_la_restauracion_viene_deshabilitada_por_defecto(entorno):
    resultado = respaldar(entorno)
    assert entorno.config.restauracion_habilitada is False
    with pytest.raises(r.OperacionNoPermitida, match="deshabilitada"):
        r.ejecutar_restauracion(resultado["id_respaldo"], 1, config=entorno.config, registro=entorno.registro)
    assert [f["operacion"] for f in entorno.registro.filas.values()] == ["RESPALDO"]


@pytest.mark.parametrize("destino", ["base; DROP", "a-b", "x" * 65, "b`c"])
def test_el_destino_de_la_restauracion_debe_ser_un_identificador_valido(entorno, destino):
    config = r.ConfigRespaldo({**entorno.env, "RESTAURACION_HABILITADA": "true", "RESTAURACION_DB_NAME": destino})
    with pytest.raises(r.OperacionNoPermitida):
        r.ejecutar_restauracion(1, 1, config=config, registro=entorno.registro)


def test_solo_se_restauran_respaldos_exitosos_y_con_archivo(entorno):
    config = r.ConfigRespaldo({**entorno.env, "RESTAURACION_HABILITADA": "true"})
    with pytest.raises(r.RespaldoNoEncontrado):
        r.ejecutar_restauracion(99, 1, config=config, registro=entorno.registro)

    fallido = entorno.registro.iniciar("RESPALDO", "MANUAL")
    entorno.registro.finalizar(fallido, "FALLIDO", 1, mensaje_error="x")
    with pytest.raises(r.RespaldoNoValido, match="terminaron correctamente"):
        r.ejecutar_restauracion(fallido, 1, config=config, registro=entorno.registro)

    restauracion = entorno.registro.iniciar("RESTAURACION", "MANUAL")
    with pytest.raises(r.RespaldoNoEncontrado):
        r.ejecutar_restauracion(restauracion, 1, config=config, registro=entorno.registro)

    resultado = respaldar(entorno)
    entorno.registro.filas[resultado["id_respaldo"]]["archivo_eliminado_en"] = "ayer"
    with pytest.raises(r.RespaldoNoEncontrado, match="retención"):
        r.ejecutar_restauracion(resultado["id_respaldo"], 1, config=config, registro=entorno.registro)


def test_la_restauracion_exige_la_huella_para_restaurar_por_archivo(entorno):
    config = r.ConfigRespaldo({**entorno.env, "RESTAURACION_HABILITADA": "true"})
    resultado = respaldar(entorno)
    os.remove(entorno.almacen / (resultado["nombre_archivo"] + ".sha256"))
    with pytest.raises(r.RespaldoNoValido, match="huella"):
        r.ejecutar_restauracion(None, 1, config=config, registro=entorno.registro, nombre_archivo=resultado["nombre_archivo"])


def test_verificar_un_respaldo_detecta_un_paquete_manipulado_despues_de_crearlo(entorno):
    resultado = respaldar(entorno)
    resumen = r.verificar_respaldo(resultado["id_respaldo"], entorno.config, entorno.registro)
    assert resumen["tablas"] == 2 and resumen["filas"] == 2

    paquete = entorno.almacen / resultado["nombre_archivo"]
    datos = bytearray(paquete.read_bytes())
    datos[100] ^= 0x01
    paquete.write_bytes(bytes(datos))
    with pytest.raises(r.RespaldoNoValido, match="SHA-256"):
        r.verificar_respaldo(resultado["id_respaldo"], entorno.config, entorno.registro)

    os.remove(paquete)
    with pytest.raises(r.RespaldoNoEncontrado):
        r.verificar_respaldo(resultado["id_respaldo"], entorno.config, entorno.registro)


def test_un_paquete_reemplazado_por_otro_valido_se_detecta_por_la_huella_registrada(entorno, tmp_path):
    resultado = respaldar(entorno)
    paquete = entorno.almacen / resultado["nombre_archivo"]
    construir_zip(tmp_path / "otro.zip", sql=VOLCADO_BASE.replace("Segunda", "Distinta"),
                  manifiesto=manifiesto_valido(VOLCADO_BASE.replace("Segunda", "Distinta")))
    paquete.write_bytes((tmp_path / "otro.zip").read_bytes())
    with pytest.raises(r.RespaldoNoValido, match="SHA-256"):
        r.verificar_respaldo(resultado["id_respaldo"], entorno.config, entorno.registro)


def test_compatibilidad_de_version_del_esquema():
    conocidas = r._migraciones_conocidas()
    assert conocidas and conocidas[-1] == "012"
    assert r._advertencias_de_version({"migraciones": conocidas}) == []
    with pytest.raises(r.RespaldoNoValido, match="más nueva"):
        r._advertencias_de_version({"migraciones": conocidas + ["999"]})
    antiguo = r._advertencias_de_version({"migraciones": conocidas[:-2]})
    assert "migrar.py" in antiguo[0] and conocidas[-1] in antiguo[0]
    # Un respaldo hecho antes de la migración 012 (registro manual de horas) se puede restaurar, con aviso.
    previo_a_012 = r._advertencias_de_version({"migraciones": [n for n in conocidas if n != "012"]})
    assert len(previo_a_012) == 1 and "faltan: 012" in previo_a_012[0] and "migrar.py" in previo_a_012[0]
    assert "No se pudo comprobar" in r._advertencias_de_version({"migraciones": None})[0]


def test_estado_del_sistema_resume_almacenamiento_y_ultimo_respaldo(entorno):
    vacio = r.estado_del_sistema(entorno.config, entorno.registro)
    assert vacio["ultimo_exitoso"] is None and vacio["restauracion_habilitada"] is False
    assert vacio["almacenamiento"]["apto"] is True, "sin carpeta todavía, pero se puede crear: el primer respaldo no queda bloqueado"
    assert niveles(vacio["almacenamiento"])["existe"] == "aviso"

    resultado = respaldar(entorno)
    estado = r.estado_del_sistema(entorno.config, entorno.registro)
    assert estado["ultimo_exitoso"]["id_respaldo"] == resultado["id_respaldo"]
    assert estado["almacenamiento"]["apto"] is True and estado["operacion_en_curso"] is False
