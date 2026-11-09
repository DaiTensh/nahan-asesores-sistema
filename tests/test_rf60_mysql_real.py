"""RF60 — Respaldo y restauración contra un servidor MySQL real y desechable.

Cada prueba trabaja sobre una base nueva con datos ficticios, en un `mysqld`
propio que se levanta en un directorio temporal y un puerto efímero (ver
tests/mysql_desechable.py). No se usa ninguna base de desarrollo ni de
producción. Si en la máquina no hay mysqld/mysqldump, el módulo se omite;
NAHAN_TEST_SIN_MYSQL=1 también lo omite.

El respaldo se hace con una cuenta que tiene exactamente los privilegios de la
cuenta de la aplicación en el servidor (sin DROP, LOCK TABLES, TRIGGER ni
PROCESS) y la restauración con una cuenta administradora del servidor
desechable.
"""
import json
import os
import re
import stat
import subprocess
import sys
import threading
import zipfile
from types import SimpleNamespace

import pytest

from backend import respaldos_programados as cli
from backend.utils import respaldos as r
from backend.utils.security import hash_password
from tests.mysql_desechable import (
    BASE_APP, CLAVE_APP, RAIZ, TABLAS_DE_NEGOCIO, USUARIO_APP, MySQLDesechable, contenido_de_tablas,
    herramientas_disponibles, sembrar_datos_ficticios,
)

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)

BASE_DESTINO = "nahan_prueba_destino"
CLAVE_ADMIN = "clave-admin-ficticia"
ADJUNTO = "aaaaaaaabbbbbbbbccccccccdddddddd.pdf"


@pytest.fixture(scope="module")
def servidor():
    servidor = MySQLDesechable().iniciar()
    yield servidor
    servidor.detener()


@pytest.fixture
def mundo(servidor, tmp_path, monkeypatch):
    """Base nueva con esquema y datos ficticios, carpeta de respaldos y de adjuntos propias."""
    root = servidor.conectar()
    cursor = root.cursor()
    for base in (BASE_APP, BASE_DESTINO):
        cursor.execute(f"DROP DATABASE IF EXISTS {base}")
        cursor.execute(f"CREATE DATABASE {base} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    root.close()
    servidor.cargar_esquema()

    cn = servidor.conectar(base=BASE_APP)
    sembrar_datos_ficticios(cn)
    cur = cn.cursor()
    cur.execute("UPDATE usuario SET password_hash = %s WHERE id_usuario = 1", (hash_password(CLAVE_ADMIN),))
    cn.commit()
    cn.close()

    adjuntos = tmp_path / "adjuntos"
    adjuntos.mkdir()
    (adjuntos / ADJUNTO).write_bytes(b"%PDF contenido ficticio original")
    almacen = tmp_path / "almacen"

    assert servidor.puerto != 3306
    entorno = {
        "DB_HOST": "127.0.0.1", "DB_PORT": str(servidor.puerto), "DB_USER": USUARIO_APP, "DB_PASSWORD": CLAVE_APP,
        "DB_NAME": BASE_APP, "RESPALDO_DIR": str(almacen), "ADJUNTOS_DIR": str(adjuntos),
        "RESTAURACION_HABILITADA": "true", "RESTAURACION_DB_USER": "root", "RESTAURACION_DB_PASSWORD": "",
    }
    for clave, valor in entorno.items():
        monkeypatch.setenv(clave, valor)
    for clave in ("RESTAURACION_DB_NAME", "RESPALDO_DB_USER", "RESPALDO_DB_PASSWORD", "RESPALDO_EXIGIR_DISPOSITIVO_SEPARADO",
                  "RESPALDO_RETENCION_MAXIMA", "MYSQLDUMP_BIN"):
        monkeypatch.delenv(clave, raising=False)

    class Mundo(SimpleNamespace):
        def conectar(self, base=BASE_APP, usuario="root", clave=""):
            return servidor.conectar(usuario=usuario, clave=clave, base=base)

        def estado(self, base=BASE_APP):
            cn = self.conectar(base)
            try:
                return contenido_de_tablas(cn)
            finally:
                cn.close()

        def historial(self):
            cn = self.conectar()
            cur = cn.cursor(dictionary=True)
            cur.execute("SELECT * FROM respaldo ORDER BY id_respaldo")
            filas = cur.fetchall()
            cn.close()
            return filas

        def auditoria(self):
            cn = self.conectar()
            cur = cn.cursor(dictionary=True)
            cur.execute("SELECT * FROM auditoria WHERE tabla_afectada = 'respaldo' ORDER BY id_auditoria")
            filas = cur.fetchall()
            cn.close()
            return filas

        def sql(self, sentencia, parametros=None, base=BASE_APP):
            cn = self.conectar(base)
            cur = cn.cursor()
            cur.execute(sentencia, parametros)
            cn.commit()
            cn.close()

        def paquete(self, id_respaldo):
            fila = next(f for f in self.historial() if f["id_respaldo"] == id_respaldo)
            return almacen / fila["nombre_archivo"]

    return Mundo(servidor=servidor, almacen=almacen, adjuntos=adjuntos, entorno=entorno)


def mutar(mundo):
    """Cambia datos y adjuntos para comprobar después que la restauración los devuelve a su estado."""
    mundo.sql("UPDATE cliente SET razon_social = 'MODIFICADO'")
    mundo.sql("DELETE FROM observacion_cliente")
    mundo.sql("DELETE FROM documento")
    mundo.sql("DELETE FROM tarea")
    mundo.sql("INSERT INTO cliente (rut, razon_social) VALUES ('99.999.999-9', 'Creado después del respaldo')")
    (mundo.adjuntos / ADJUNTO).write_bytes(b"CONTENIDO MODIFICADO")
    (mundo.adjuntos / "posterior.pdf").write_bytes(b"adjunto creado despues")


# ---------------------------------------------------------------------------
# Respaldo (CA2, CA3, CA5)
# ---------------------------------------------------------------------------

def test_la_cuenta_de_la_aplicacion_no_tiene_privilegios_de_destruccion(mundo):
    cn = mundo.conectar(usuario=USUARIO_APP, clave=CLAVE_APP)
    cur = cn.cursor()
    cur.execute("SHOW GRANTS")
    concesiones = " ".join(f[0] for f in cur.fetchall()).upper()
    cn.close()
    for privilegio in ("DROP", "LOCK TABLES", "TRIGGER", "PROCESS", "ALL PRIVILEGES"):
        assert privilegio not in concesiones


def test_respaldo_con_privilegios_minimos_genera_un_paquete_valido_y_completo(mundo):
    antes = mundo.estado()
    resultado = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)

    paquete = mundo.almacen / resultado["nombre_archivo"]
    assert r.PATRON_NOMBRE_PAQUETE.match(paquete.name)
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(paquete).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(mundo.almacen).st_mode) == 0o700

    manifiesto = resultado["manifiesto"]
    contadas = {tabla: len(filas) for tabla, filas in antes.items()}
    assert manifiesto["base_de_datos"]["tablas"] == contadas, "el manifiesto refleja exactamente la base respaldada"
    assert not {"respaldo", "intento_login_fallido"} & set(manifiesto["base_de_datos"]["tablas"])
    assert set(manifiesto["base_de_datos"]["tablas"]) == set(TABLAS_DE_NEGOCIO)
    assert manifiesto["migraciones"] == ["001", "002", "003", "004", "005", "006", "007", "008", "009", "010", "011", "012"]
    assert list(manifiesto["adjuntos"]["archivos"]) == [ADJUNTO]
    assert "mysqldump" in manifiesto["herramienta"]

    fila = mundo.historial()[0]
    assert (fila["operacion"], fila["tipo"], fila["estado"], fila["id_usuario"]) == ("RESPALDO", "MANUAL", "EXITOSO", 1)
    assert fila["fecha_inicio"] is not None and fila["fecha_fin"] is not None and fila["fecha_fin"] >= fila["fecha_inicio"]
    assert fila["sha256"] == resultado["sha256"] and fila["tamano_bytes"] == paquete.stat().st_size
    assert fila["nombre_archivo"] == paquete.name and fila["mensaje_error"] is None
    assert float(fila["duracion_segundos"]) >= 0

    resumen = r.verificar_respaldo(fila["id_respaldo"])
    assert resumen["tablas"] == 22 and resumen["adjuntos"] == 1


def test_el_paquete_no_contiene_credenciales_ni_la_tabla_de_historial(mundo):
    resultado = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    with zipfile.ZipFile(mundo.almacen / resultado["nombre_archivo"]) as zf:
        contenido = b"".join(zf.read(n) for n in zf.namelist())
        sql = zf.read("base_de_datos.sql").decode("utf-8")
        manifiesto = zf.read("manifest.json")
    assert CLAVE_APP.encode() not in contenido and b"root" not in manifiesto
    assert "`respaldo`" not in sql
    assert "CREATE DATABASE" not in sql and "USE `" not in sql, "el volcado no depende del nombre de la base"
    assert not [n for n in os.listdir(mundo.almacen) if n.startswith((".parcial", ".trabajo"))]


def test_el_volcado_conserva_tildes_comillas_saltos_de_linea_y_simbolos(mundo):
    resultado = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    with zipfile.ZipFile(mundo.almacen / resultado["nombre_archivo"]) as zf:
        sql = zf.read("base_de_datos.sql").decode("utf-8")
    for texto in ("Ñandú y Compañía «Ficticia»", "Declaración «Renta» 2026", "✓"):
        assert texto in sql
    assert sql.rstrip().splitlines()[-1].startswith("-- Dump completed")


def test_respaldo_manual_por_api_deja_historial_y_auditoria(client, iniciar_sesion, mundo):
    iniciar_sesion(usuario_id=1, rol_id=1, nombre="Admin Ficticia")
    respuesta = client.post("/api/respaldos")
    assert respuesta.status_code == 201, respuesta.get_json()
    id_respaldo = respuesta.get_json()["respaldo"]["id_respaldo"]

    historial = client.get("/api/respaldos").get_json()["respaldos"]
    assert len(historial) == 1
    fila = historial[0]
    assert (fila["id_respaldo"], fila["estado"], fila["tipo"], fila["usuario"]) == (id_respaldo, "EXITOSO", "MANUAL", "Admin Ficticia")
    assert re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$", fila["fecha_inicio"]) and fila["archivo_disponible"] is True
    assert str(mundo.almacen) not in json.dumps(historial)

    eventos = mundo.auditoria()
    assert len(eventos) == 1
    assert (eventos[0]["id_usuario"], eventos[0]["accion"], eventos[0]["id_registro"]) == (1, "RESPALDO_MANUAL", id_respaldo)
    assert fila["sha256"] in eventos[0]["datos_nuevos"] and CLAVE_APP not in eventos[0]["datos_nuevos"]

    # RF49 (cambios recientes) y RF56 (historial) muestran el evento sin cambios adicionales.
    filtros = client.get("/api/cambios-recientes/filtros").get_json()
    assert "Respaldos" in filtros["modulos"]
    cambios = client.get("/api/cambios-recientes", query_string={"modulo": "Respaldos"}).get_json()["cambios"]
    assert [(c["tipo"], c["modulo"]) for c in cambios] == [("RESPALDO_MANUAL", "Respaldos")]
    historial_global = client.get("/api/historial", query_string={"modulo": "Respaldos"}).get_json()
    assert historial_global["total"] == 1


def test_un_respaldo_manual_fallido_por_api_queda_en_historial_y_auditoria(client, iniciar_sesion, mundo, monkeypatch):
    iniciar_sesion(usuario_id=1, rol_id=1)
    monkeypatch.setenv("MYSQLDUMP_BIN", str(mundo.almacen.parent / "no_existe"))
    respuesta = client.post("/api/respaldos")
    assert respuesta.status_code == 500 and "MYSQLDUMP_BIN" in respuesta.get_json()["error"]
    fila = mundo.historial()[0]
    assert fila["estado"] == "FALLIDO" and "mysqldump" in fila["mensaje_error"] and fila["nombre_archivo"] is None
    assert [e["accion"] for e in mundo.auditoria()] == ["RESPALDO_MANUAL_FALLIDO"]
    assert list(mundo.almacen.glob("*.zip")) == []


def test_credenciales_de_respaldo_incorrectas_fallan_sin_filtrar_la_contrasena(mundo, monkeypatch, caplog):
    """La cuenta del respaldo es otra que la del historial: el intento fallido queda registrado."""
    monkeypatch.setenv("RESPALDO_DB_USER", USUARIO_APP)
    monkeypatch.setenv("RESPALDO_DB_PASSWORD", "contraseña-incorrecta-ficticia")
    with pytest.raises(r.ErrorRespaldo) as info:
        r.ejecutar_respaldo(r.TIPO_PROGRAMADO)
    fila = mundo.historial()[0]
    assert fila["estado"] == "FALLIDO" and "1045" in fila["mensaje_error"]
    for texto in (str(info.value), fila["mensaje_error"], caplog.text):
        assert "contraseña-incorrecta-ficticia" not in texto
    assert list(mundo.almacen.glob("*.zip")) == []


def test_sin_acceso_a_la_base_el_respaldo_falla_con_un_mensaje_controlado(mundo, monkeypatch, caplog, capsys):
    monkeypatch.setenv("DB_PASSWORD", "contraseña-incorrecta-ficticia")
    with pytest.raises(r.ErrorRespaldo, match="No se pudo conectar a la base de datos") as info:
        r.ejecutar_respaldo(r.TIPO_PROGRAMADO)
    salida = capsys.readouterr()
    for texto in (str(info.value), caplog.text, salida.out, salida.err):
        assert "contraseña-incorrecta-ficticia" not in texto
    assert cli.main([]) == cli.SALIDA_ERROR
    assert list(mundo.almacen.glob("*.zip")) == []


def test_el_almacenamiento_invalido_registra_el_intento_fallido(mundo, monkeypatch):
    monkeypatch.setenv("RESPALDO_DIR", os.path.join(RAIZ, "respaldos_dentro_del_proyecto"))
    with pytest.raises(r.AlmacenamientoNoValido):
        r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    assert not os.path.exists(os.path.join(RAIZ, "respaldos_dentro_del_proyecto"))
    assert [(f["estado"], f["tipo"]) for f in mundo.historial()] == [("FALLIDO", "MANUAL")]


@pytest.mark.skipif(os.name != "posix" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="requiere usuario sin privilegios")
def test_un_error_de_permisos_en_el_almacenamiento_se_informa(mundo):
    os.mkdir(mundo.almacen, 0o700)
    os.chmod(mundo.almacen, 0o500)
    try:
        with pytest.raises(r.AlmacenamientoNoValido, match="escribir"):
            r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    finally:
        os.chmod(mundo.almacen, 0o700)
    assert mundo.historial()[0]["estado"] == "FALLIDO"


def test_los_respaldos_huerfanos_se_cierran_como_fallidos(mundo):
    mundo.sql("INSERT INTO respaldo (operacion, tipo, estado) VALUES ('RESPALDO', 'PROGRAMADO', 'EN_CURSO')")
    r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    estados = [(f["estado"], f["mensaje_error"]) for f in mundo.historial()]
    assert estados[0][0] == "FALLIDO" and "Interrumpido" in estados[0][1] and estados[1] == ("EXITOSO", None)


def test_la_retencion_conserva_solo_los_paquetes_mas_recientes(mundo, monkeypatch):
    monkeypatch.setenv("RESPALDO_RETENCION_MAXIMA", "3")
    ids = [r.ejecutar_respaldo(r.TIPO_PROGRAMADO)["id_respaldo"] for _ in range(5)]
    assert len(list(mundo.almacen.glob("*.zip"))) == 3 and len(list(mundo.almacen.glob("*.sha256"))) == 3
    filas = {f["id_respaldo"]: f for f in mundo.historial()}
    assert [bool(filas[i]["archivo_eliminado_en"]) for i in ids] == [True, True, False, False, False]
    assert all(f["estado"] == "EXITOSO" for f in filas.values())
    with pytest.raises(r.RespaldoNoEncontrado, match="retención"):
        r.verificar_respaldo(ids[0])


# ---------------------------------------------------------------------------
# Programación (CA1)
# ---------------------------------------------------------------------------

def test_la_ejecucion_programada_desde_consola_registra_un_respaldo_programado(mundo, capsys):
    assert cli.main([]) == cli.SALIDA_OK
    fila = mundo.historial()[0]
    assert (fila["tipo"], fila["estado"], fila["id_usuario"]) == ("PROGRAMADO", "EXITOSO", None)
    assert (mundo.almacen / fila["nombre_archivo"]).exists()
    assert mundo.auditoria() == [], "los respaldos programados no tienen usuario; su constancia es la tabla respaldo"

    assert cli.main(["estado"]) == cli.SALIDA_OK
    assert "Último respaldo exitoso: #1 (PROGRAMADO" in capsys.readouterr().out
    assert cli.main(["verificar", "--id", str(fila["id_respaldo"])]) == cli.SALIDA_OK
    assert cli.main(["respaldar", "--tipo", "manual"]) == cli.SALIDA_OK
    assert [f["tipo"] for f in mundo.historial()] == ["PROGRAMADO", "MANUAL"]


def test_el_punto_de_entrada_de_systemd_funciona_como_proceso_independiente(mundo):
    """Lo mismo que ejecuta nahan-respaldo.service: `python -m backend.respaldos_programados`."""
    entorno = {**os.environ, **mundo.entorno, "PYTHONDONTWRITEBYTECODE": "1"}
    proceso = subprocess.run([sys.executable, "-m", "backend.respaldos_programados"], cwd=RAIZ, env=entorno,
                             capture_output=True, text=True, timeout=120)
    assert proceso.returncode == 0, proceso.stderr
    assert "Respaldo 1 completado" in proceso.stderr
    assert CLAVE_APP not in proceso.stdout + proceso.stderr
    assert mundo.historial()[0]["tipo"] == "PROGRAMADO"


def test_una_falla_programada_sale_con_codigo_de_error_y_queda_registrada(mundo, monkeypatch):
    monkeypatch.setenv("RESPALDO_DIR", "")
    assert cli.main([]) == cli.SALIDA_ERROR
    fila = mundo.historial()[0]
    assert (fila["tipo"], fila["estado"]) == ("PROGRAMADO", "FALLIDO") and "RESPALDO_DIR" in fila["mensaje_error"]


def test_un_respaldo_programado_no_se_solapa_con_uno_en_curso(mundo, monkeypatch):
    r.preparar_almacenamiento(r.ConfigRespaldo())
    with r._Bloqueo(str(mundo.almacen / r.ARCHIVO_BLOQUEO)):
        assert cli.main([]) == cli.SALIDA_OCUPADO
    assert mundo.historial() == [], "una ejecución rechazada por bloqueo no deja filas"
    assert cli.main([]) == cli.SALIDA_OK


def test_dos_procesos_simultaneos_solo_dejan_pasar_a_uno(mundo, monkeypatch):
    dentro, soltar = threading.Event(), threading.Event()
    original = r._volcar_base

    def lento(config, ruta_sql):
        dentro.set()
        assert soltar.wait(30)
        original(config, ruta_sql)
    monkeypatch.setattr(r, "_volcar_base", lento)

    resultados = []
    hilo = threading.Thread(target=lambda: resultados.append(cli.main([])))
    hilo.start()
    assert dentro.wait(30)
    try:
        assert [f["estado"] for f in mundo.historial()] == ["EN_CURSO"]
        monkeypatch.setattr(r, "_volcar_base", original)
        assert cli.main(["respaldar", "--tipo", "manual"]) == cli.SALIDA_OCUPADO
    finally:
        soltar.set()
        hilo.join(60)
    assert resultados == [cli.SALIDA_OK]
    assert [f["estado"] for f in mundo.historial()] == ["EXITOSO"]


def test_un_respaldo_manual_por_api_se_rechaza_si_hay_uno_en_curso(client, iniciar_sesion, mundo, monkeypatch):
    iniciar_sesion(usuario_id=1, rol_id=1)
    r.preparar_almacenamiento(r.ConfigRespaldo())
    with r._Bloqueo(str(mundo.almacen / r.ARCHIVO_BLOQUEO)):
        respuesta = client.post("/api/respaldos")
    assert respuesta.status_code == 409 and respuesta.get_json()["codigo"] == "OPERACION_EN_CURSO"
    assert mundo.historial() == [] and mundo.auditoria() == []


# ---------------------------------------------------------------------------
# Restauración (CA4)
# ---------------------------------------------------------------------------

def test_restauracion_correcta_en_entorno_aislado(mundo):
    antes = mundo.estado()
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mutar(mundo)
    assert mundo.estado() != antes

    resultado = r.ejecutar_restauracion(respaldo["id_respaldo"], 1)

    despues = mundo.estado()
    assert despues == antes, [t for t in antes if antes[t] != despues[t]]
    assert (mundo.adjuntos / ADJUNTO).read_bytes() == b"%PDF contenido ficticio original"
    assert (mundo.adjuntos / "posterior.pdf").exists(), "la restauración no borra adjuntos"

    historial = {f["id_respaldo"]: f for f in mundo.historial()}
    assert historial[respaldo["id_respaldo"]]["estado"] == "EXITOSO", "el historial sobrevive a la restauración"
    restauracion = historial[resultado["id_restauracion"]]
    previo = historial[resultado["id_previo"]]
    assert (restauracion["operacion"], restauracion["estado"], restauracion["id_relacionado"], restauracion["id_usuario"]) == \
        ("RESTAURACION", "EXITOSO", respaldo["id_respaldo"], 1)
    assert (previo["operacion"], previo["tipo"], previo["estado"], previo["id_relacionado"]) == \
        ("RESPALDO", "PREVIO_RESTAURACION", "EXITOSO", resultado["id_restauracion"])
    assert restauracion["fecha_fin"] >= restauracion["fecha_inicio"] and "copia previa=" in restauracion["detalle"]
    assert not (mundo.almacen / r.ARCHIVO_MANTENIMIENTO).exists()
    assert not [n for n in os.listdir(mundo.almacen) if n.startswith(".trabajo")]


def test_la_copia_previa_guarda_el_estado_que_se_reemplaza(mundo):
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mutar(mundo)
    mutado = mundo.estado()
    resultado = r.ejecutar_restauracion(respaldo["id_respaldo"], 1)

    r.ejecutar_restauracion(resultado["id_previo"], 1)  # volver al estado previo a la restauración

    assert mundo.estado() == mutado
    assert (mundo.adjuntos / ADJUNTO).read_bytes() == b"CONTENIDO MODIFICADO"


def test_la_restauracion_conserva_la_integridad_referencial_y_los_autoincrementales(mundo):
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mutar(mundo)
    r.ejecutar_restauracion(respaldo["id_respaldo"], 1)

    cn = mundo.conectar()
    cur = cn.cursor()
    cur.execute("SELECT COUNT(*) FROM tarea t LEFT JOIN cliente c ON c.id_cliente = t.id_cliente WHERE c.id_cliente IS NULL")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM documento d LEFT JOIN usuario u ON u.id_usuario = d.subido_por WHERE u.id_usuario IS NULL")
    assert cur.fetchone()[0] == 0
    cur.execute("INSERT INTO cliente (rut, razon_social) VALUES ('33.333.333-3', 'Posterior')")
    assert cur.lastrowid == 3, "AUTO_INCREMENT continúa donde estaba en el respaldo"
    cur.execute("SELECT @@foreign_key_checks")
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT COUNT(*) FROM information_schema.table_constraints WHERE table_schema = %s AND constraint_type = 'FOREIGN KEY'", (BASE_APP,))
    assert cur.fetchone()[0] >= 15, "las claves foráneas se recrean"
    cn.rollback()
    cn.close()


def test_restauracion_por_api_exige_confirmacion_y_contrasena_y_queda_auditada(client, iniciar_sesion, mundo):
    iniciar_sesion(usuario_id=1, rol_id=1, nombre="Admin Ficticia")
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mutar(mundo)
    mutado = mundo.estado()
    ruta = f"/api/respaldos/{respaldo['id_respaldo']}/restaurar"

    assert client.post(ruta, json={"confirmacion": "RESTAURAR", "password": "equivocada"}).status_code == 403
    assert client.post(ruta, json={"confirmacion": "si", "password": CLAVE_ADMIN}).status_code == 400
    assert {k: v for k, v in mundo.estado().items() if k != "auditoria"} == {k: v for k, v in mutado.items() if k != "auditoria"}, \
        "los intentos rechazados no tocan la base"
    assert [e["accion"] for e in mundo.auditoria()] == ["RESTAURACION_RECHAZADA"], "el intento con contraseña errónea queda auditado"
    assert [f["operacion"] for f in mundo.historial()] == ["RESPALDO"]

    respuesta = client.post(ruta, json={"confirmacion": "RESTAURAR", "password": CLAVE_ADMIN})
    assert respuesta.status_code == 200, respuesta.get_json()
    assert CLAVE_ADMIN not in respuesta.get_data(as_text=True)
    assert mundo.estado()["cliente"][0][2] != "MODIFICADO"

    acciones = [(e["accion"], e["id_usuario"]) for e in mundo.auditoria()]
    assert acciones == [("RESTAURACION_RESPALDO", 1)]
    assert CLAVE_ADMIN not in str(mundo.auditoria())

    listado = client.get("/api/respaldos").get_json()["respaldos"]
    assert [f["operacion"] for f in listado] == ["RESPALDO", "RESTAURACION", "RESPALDO"]
    assert client.post(f"/api/respaldos/{respaldo['id_respaldo']}/verificar").status_code == 200


def test_el_limite_de_confirmaciones_rechazadas_se_aplica_con_mysql_real(client, iniciar_sesion, mundo):
    iniciar_sesion(usuario_id=1, rol_id=1)
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mutar(mundo)
    mutado = mundo.estado()
    ruta = f"/api/respaldos/{respaldo['id_respaldo']}/restaurar"
    mala = {"confirmacion": "RESTAURAR", "password": "equivocada"}
    buena = {"confirmacion": "RESTAURAR", "password": CLAVE_ADMIN}

    assert [client.post(ruta, json=mala).status_code for _ in range(5)] == [403] * 5
    assert client.post(ruta, json=mala).status_code == 429
    bloqueada = client.post(ruta, json=buena)
    assert bloqueada.status_code == 429 and bloqueada.headers["Retry-After"] == "900"
    assert {k: v for k, v in mundo.estado().items() if k != "auditoria"} == {k: v for k, v in mutado.items() if k != "auditoria"}
    assert [e["accion"] for e in mundo.auditoria()] == ["RESTAURACION_RECHAZADA"] * 5

    mundo.sql("UPDATE auditoria SET fecha = DATE_SUB(NOW(), INTERVAL 20 MINUTE) WHERE accion = 'RESTAURACION_RECHAZADA'")
    assert client.post(ruta, json=buena).status_code == 200, "pasada la ventana, la contraseña correcta vuelve a funcionar"


def test_la_restauracion_deshabilitada_no_toca_nada(client, iniciar_sesion, mundo, monkeypatch):
    iniciar_sesion(usuario_id=1, rol_id=1)
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mutar(mundo)
    mutado = mundo.estado()
    monkeypatch.setenv("RESTAURACION_HABILITADA", "false")

    respuesta = client.post(f"/api/respaldos/{respaldo['id_respaldo']}/restaurar",
                            json={"confirmacion": "RESTAURAR", "password": CLAVE_ADMIN})
    assert respuesta.status_code == 403 and respuesta.get_json()["codigo"] == "OPERACION_NO_PERMITIDA"
    assert [e["accion"] for e in mundo.auditoria()] == ["RESTAURACION_FALLIDA"]
    assert {k: v for k, v in mundo.estado().items() if k != "auditoria"} == {k: v for k, v in mutado.items() if k != "auditoria"}
    assert client.get("/api/respaldos/estado").get_json()["restauracion_habilitada"] is False


def test_un_paquete_manipulado_se_rechaza_antes_de_tocar_la_base(mundo):
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mutar(mundo)
    mutado = mundo.estado()
    paquete = mundo.paquete(respaldo["id_respaldo"])
    datos = bytearray(paquete.read_bytes())
    datos[len(datos) // 2] ^= 0x01
    paquete.write_bytes(bytes(datos))

    with pytest.raises(r.RespaldoNoValido) as info:
        r.ejecutar_restauracion(respaldo["id_respaldo"], 1)

    assert mundo.estado() == mutado
    assert (mundo.adjuntos / ADJUNTO).read_bytes() == b"CONTENIDO MODIFICADO"
    fila = [f for f in mundo.historial() if f["operacion"] == "RESTAURACION"][0]
    assert fila["estado"] == "FALLIDO" and fila["mensaje_error"] == f"{info.value.mensaje} La base de datos no fue modificada."
    assert not [f for f in mundo.historial() if f["tipo"] == "PREVIO_RESTAURACION"], "no hay copia previa si no se llegó a restaurar"
    assert not (mundo.almacen / r.ARCHIVO_MANTENIMIENTO).exists()


def test_un_paquete_reemplazado_por_otro_distinto_se_rechaza(mundo):
    primero = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mundo.sql("UPDATE cliente SET razon_social = 'Otra versión'")
    segundo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    estado = mundo.estado()
    mundo.paquete(primero["id_respaldo"]).write_bytes(mundo.paquete(segundo["id_respaldo"]).read_bytes())

    with pytest.raises(r.RespaldoNoValido, match="SHA-256"):
        r.ejecutar_restauracion(primero["id_respaldo"], 1)
    assert mundo.estado() == estado


def test_un_volcado_con_sentencias_peligrosas_no_se_ejecuta_aunque_el_paquete_sea_coherente(mundo):
    """Un atacante con acceso al archivo puede rehacer manifiesto y huella; las sentencias ajenas se rechazan igual."""
    import hashlib
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    paquete = mundo.paquete(respaldo["id_respaldo"])
    with zipfile.ZipFile(paquete) as zf:
        sql = zf.read("base_de_datos.sql").decode()
        adjuntos = {n: zf.read(n) for n in zf.namelist() if n.startswith("adjuntos/")}
    maligno = sql.replace("-- Dump completed", "CREATE USER 'intruso'@'%' IDENTIFIED BY 'x';\n\\! touch /tmp/nahan_pwned\n-- Dump completed")
    manifiesto = respaldo["manifiesto"]
    manifiesto["base_de_datos"]["sha256"] = hashlib.sha256(maligno.encode()).hexdigest()
    manifiesto["base_de_datos"]["bytes"] = len(maligno.encode())
    with zipfile.ZipFile(paquete, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifiesto))
        zf.writestr("base_de_datos.sql", maligno)
        for nombre, contenido in adjuntos.items():
            zf.writestr(nombre, contenido)
    mundo.sql("UPDATE respaldo SET sha256 = %s WHERE id_respaldo = %s", (r._sha256_archivo(str(paquete)), respaldo["id_respaldo"]))
    estado = mundo.estado()

    with pytest.raises(r.RespaldoNoValido, match="no admitida"):
        r.ejecutar_restauracion(respaldo["id_respaldo"], 1)

    assert mundo.estado() == estado and not os.path.exists("/tmp/nahan_pwned")
    cn = mundo.conectar(base=None)
    cur = cn.cursor()
    cur.execute("SELECT COUNT(*) FROM mysql.user WHERE user = 'intruso'")
    assert cur.fetchone()[0] == 0
    cn.close()


def paquete_con_fallo_a_medias(mundo, respaldo):
    """Reemplaza el paquete por uno coherente (huella y manifiesto al día) cuyo volcado falla en MySQL a mitad de la carga."""
    paquete = mundo.paquete(respaldo["id_respaldo"])
    with zipfile.ZipFile(paquete) as zf:
        sql = zf.read("base_de_datos.sql").decode()
        adjuntos = {n: zf.read(n) for n in zf.namelist() if n.startswith("adjuntos/")}
    linea = next(l for l in sql.splitlines() if l.startswith("INSERT INTO `cliente`"))
    roto = sql.replace(linea, linea + "\n" + linea, 1)  # misma fila dos veces: viola la clave primaria
    destino = mundo.almacen / "roto.tmp"
    with zipfile.ZipFile(destino, "w") as zf:
        import hashlib
        manifiesto = respaldo["manifiesto"]
        manifiesto["base_de_datos"]["sha256"] = hashlib.sha256(roto.encode()).hexdigest()
        manifiesto["base_de_datos"]["bytes"] = len(roto.encode())
        manifiesto["base_de_datos"]["tablas"]["cliente"] += 1
        zf.writestr("manifest.json", json.dumps(manifiesto))
        zf.writestr("base_de_datos.sql", roto)
        for nombre, contenido in adjuntos.items():
            zf.writestr(nombre, contenido)
    os.replace(destino, paquete)
    mundo.sql("UPDATE respaldo SET sha256 = %s WHERE id_respaldo = %s", (r._sha256_archivo(str(paquete)), respaldo["id_respaldo"]))


def test_una_restauracion_que_falla_a_medias_vuelve_al_estado_anterior(mundo):
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    paquete_con_fallo_a_medias(mundo, respaldo)
    mutar(mundo)
    mutado = mundo.estado()

    with pytest.raises(r.ErrorRespaldo) as info:
        r.ejecutar_restauracion(respaldo["id_respaldo"], 1)

    assert "1062" in info.value.mensaje
    assert info.value.recuperacion.startswith("Se restableció automáticamente")
    assert mundo.estado() == mutado, "la recuperación automática devolvió exactamente el estado previo"
    assert (mundo.adjuntos / ADJUNTO).read_bytes() == b"CONTENIDO MODIFICADO"

    filas = {f["operacion"] + f["tipo"]: f for f in mundo.historial() if f["id_respaldo"] != respaldo["id_respaldo"]}
    assert filas["RESTAURACIONMANUAL"]["estado"] == "FALLIDO"
    assert "Se restableció automáticamente" in filas["RESTAURACIONMANUAL"]["mensaje_error"]
    assert filas["RESPALDOPREVIO_RESTAURACION"]["estado"] == "EXITOSO"
    assert not (mundo.almacen / r.ARCHIVO_MANTENIMIENTO).exists()


def test_una_falla_al_copiar_adjuntos_tambien_se_recupera(mundo, monkeypatch):
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mutar(mundo)
    mutado = mundo.estado()
    original = r._copiar_adjuntos
    llamadas = []

    def falla_la_primera_vez(*args, **kwargs):
        llamadas.append(1)
        if len(llamadas) == 1:
            raise r.ErrorRespaldo("disco lleno (simulado)")
        return original(*args, **kwargs)
    monkeypatch.setattr(r, "_copiar_adjuntos", falla_la_primera_vez)

    with pytest.raises(r.ErrorRespaldo, match="disco lleno"):
        r.ejecutar_restauracion(respaldo["id_respaldo"], 1)
    assert mundo.estado() == mutado
    assert (mundo.adjuntos / ADJUNTO).read_bytes() == b"CONTENIDO MODIFICADO"


def test_si_tampoco_se_puede_recuperar_se_indica_el_paquete_previo(mundo, monkeypatch):
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    paquete_con_fallo_a_medias(mundo, respaldo)
    monkeypatch.setattr(r, "_aplicar_paquete", lambda *a, **k: (_ for _ in ()).throw(r.ErrorRespaldo("sin disco")))

    with pytest.raises(r.ErrorRespaldo) as info:
        r.ejecutar_restauracion(respaldo["id_respaldo"], 1)
    previo = next(f for f in mundo.historial() if f["tipo"] == "PREVIO_RESTAURACION")
    assert "No se pudo restablecer automáticamente" in info.value.recuperacion
    assert previo["nombre_archivo"] in info.value.recuperacion


def test_sin_privilegios_para_restaurar_se_informa_antes_de_tocar_la_base(mundo, monkeypatch):
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mutar(mundo)
    mutado = mundo.estado()
    monkeypatch.setenv("RESTAURACION_DB_USER", USUARIO_APP)
    monkeypatch.setenv("RESTAURACION_DB_PASSWORD", CLAVE_APP)

    with pytest.raises(r.ErrorRespaldo, match="privilegios necesarios"):
        r.ejecutar_restauracion(respaldo["id_respaldo"], 1)
    assert mundo.estado() == mutado
    assert not [f for f in mundo.historial() if f["tipo"] == "PREVIO_RESTAURACION"]
    assert "La base de datos no fue modificada" in [f for f in mundo.historial() if f["operacion"] == "RESTAURACION"][0]["mensaje_error"]


def test_un_ensayo_de_restauracion_en_otra_base_no_toca_la_activa(mundo, monkeypatch):
    antes = mundo.estado()
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mutar(mundo)
    mutado = mundo.estado()
    monkeypatch.setenv("RESTAURACION_DB_NAME", BASE_DESTINO)

    resultado = r.ejecutar_restauracion(respaldo["id_respaldo"], 1)

    assert mundo.estado(BASE_DESTINO) == antes
    assert mundo.estado() == mutado, "la base activa no cambió"
    assert (mundo.adjuntos / ADJUNTO).read_bytes() == b"CONTENIDO MODIFICADO", "los adjuntos activos no se tocan en un ensayo"
    assert resultado["id_previo"] is None
    detalle = [f for f in mundo.historial() if f["operacion"] == "RESTAURACION"][0]["detalle"]
    assert f"«{BASE_DESTINO}»" in detalle


def test_recuperacion_total_sin_historial_desde_el_paquete_y_su_huella(mundo, capsys):
    antes = mundo.estado()
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    nombre = mundo.paquete(respaldo["id_respaldo"]).name
    root = mundo.conectar(base=None)
    cur = root.cursor()
    cur.execute(f"DROP DATABASE {BASE_APP}")
    cur.execute(f"CREATE DATABASE {BASE_APP} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    root.close()
    (mundo.adjuntos / ADJUNTO).unlink()

    assert cli.main(["restaurar", "--archivo", nombre, "--confirmo-base", "otra_base"]) == cli.SALIDA_ERROR
    assert cli.main(["restaurar", "--archivo", nombre, "--confirmo-base", BASE_APP]) == cli.SALIDA_OK

    assert mundo.estado() == antes
    assert (mundo.adjuntos / ADJUNTO).read_bytes() == b"%PDF contenido ficticio original"
    cn = mundo.conectar()
    cur = cn.cursor()
    cur.execute("SHOW TABLES LIKE 'respaldo'")
    assert cur.fetchall() == [], "el historial no viaja en el paquete: se recrea con la migración 010"
    cn.close()
    assert "Restauración completada" in capsys.readouterr().out


def test_la_recuperacion_por_archivo_exige_que_la_huella_coincida(mundo):
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    paquete = mundo.paquete(respaldo["id_respaldo"])
    mutar(mundo)
    mutado = mundo.estado()
    datos = bytearray(paquete.read_bytes())
    datos[200] ^= 0x01
    paquete.write_bytes(bytes(datos))

    assert cli.main(["restaurar", "--archivo", paquete.name, "--confirmo-base", BASE_APP]) == cli.SALIDA_ERROR
    assert mundo.estado() == mutado
    os.remove(str(paquete) + ".sha256")
    assert cli.main(["restaurar", "--archivo", paquete.name, "--confirmo-base", BASE_APP]) == cli.SALIDA_ERROR
    assert cli.main(["restaurar", "--archivo", "../" + paquete.name, "--confirmo-base", BASE_APP]) == cli.SALIDA_ERROR


def test_el_conteo_de_filas_posterior_a_la_carga_detecta_diferencias(mundo, tmp_path):
    """Red de seguridad si, a pesar de la validación previa, la base de destino no queda como el manifiesto."""
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    carpeta = tmp_path / "extraccion"
    carpeta.mkdir()
    manifiesto = r.abrir_paquete(str(mundo.paquete(respaldo["id_respaldo"])), r.ConfigRespaldo(), extraer_en=str(carpeta))
    tablas = dict(manifiesto["base_de_datos"]["tablas"])
    config = r.ConfigRespaldo()

    r._cargar_volcado(config, str(carpeta / "base_de_datos.sql"), tablas)

    tablas["cliente"] += 1
    with pytest.raises(r.ErrorRespaldo, match="«cliente» quedó con 2 filas y el respaldo tiene 3"):
        r._cargar_volcado(config, str(carpeta / "base_de_datos.sql"), tablas)


def test_los_intentos_de_login_fallidos_no_se_revierten_al_restaurar(mundo):
    """SEC-02 es estado operativo: restaurar un respaldo antiguo no debe «perdonar» intentos recientes."""
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mundo.sql("INSERT INTO intento_login_fallido (clave_cuenta, ip_cliente, id_usuario, fecha) VALUES (%s, NULL, NULL, UTC_TIMESTAMP())",
              (b"\x01" * 32,))
    mutar(mundo)
    r.ejecutar_restauracion(respaldo["id_respaldo"], 1)
    cn = mundo.conectar()
    cur = cn.cursor()
    cur.execute("SELECT COUNT(*) FROM intento_login_fallido")
    assert cur.fetchone()[0] == 1
    cn.close()


def test_la_restauracion_exige_que_el_servidor_pueda_confirmar_la_base_de_destino(mundo, monkeypatch):
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    monkeypatch.setenv("RESTAURACION_DB_NAME", "base_que_no_existe")
    with pytest.raises(r.ErrorRespaldo, match="No se pudo conectar"):
        r.ejecutar_restauracion(respaldo["id_respaldo"], 1)


def test_restauracion_con_muchos_registros(mundo):
    cn = mundo.conectar()
    cur = cn.cursor()
    cur.executemany("INSERT INTO cliente (rut, razon_social) VALUES (%s, %s)",
                    [(f"7{n:07d}-0", f"Cliente masivo ñ {n}") for n in range(2600)])
    cn.commit()
    cn.close()
    antes = mundo.estado()
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    assert respaldo["manifiesto"]["base_de_datos"]["tablas"]["cliente"] == 2602

    mundo.sql("DELETE FROM cliente WHERE rut LIKE '7%'")
    r.ejecutar_restauracion(respaldo["id_respaldo"], 1)
    assert mundo.estado() == antes


def test_durante_la_restauracion_la_api_responde_503_y_despues_se_recupera(client, iniciar_sesion, mundo, monkeypatch):
    iniciar_sesion(usuario_id=1, rol_id=1)
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    dentro, soltar = threading.Event(), threading.Event()
    original = r._cargar_volcado

    def pausada(*args, **kwargs):
        dentro.set()
        assert soltar.wait(30)
        return original(*args, **kwargs)
    monkeypatch.setattr(r, "_cargar_volcado", pausada)

    resultados = []
    hilo = threading.Thread(target=lambda: resultados.append(r.ejecutar_restauracion(respaldo["id_respaldo"], 1)))
    hilo.start()
    assert dentro.wait(30)
    try:
        for ruta in ("/api/respaldos", "/api/clientes", "/api/auth/me"):
            respuesta = client.get(ruta)
            assert respuesta.status_code == 503 and respuesta.get_json()["codigo"] == "MANTENIMIENTO", ruta
        assert (mundo.almacen / r.ARCHIVO_MANTENIMIENTO).exists()
        with pytest.raises(r.OperacionEnCurso):
            r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    finally:
        soltar.set()
        hilo.join(60)
    assert len(resultados) == 1
    assert client.get("/api/respaldos").status_code == 200


# ---------------------------------------------------------------------------
# Compatibilidad con RF47 y RF49, migración y esquema
# ---------------------------------------------------------------------------

def test_rf47_clientes_recientes_sobrevive_a_una_restauracion(client, iniciar_sesion, mundo):
    iniciar_sesion(usuario_id=1, rol_id=1)
    mundo.sql("INSERT INTO cliente_reciente (id_usuario, id_cliente, fecha_interaccion) VALUES (1, 2, '2026-11-01 10:00:00.123456')")
    mundo.sql("UPDATE parametros_sistema SET valor_parametro = '7' WHERE nombre_parametro = 'CLIENTES_RECIENTES_LIMITE'")
    antes = client.get("/api/clientes/recientes").get_json()
    assert [c["id_cliente"] for c in antes["clientes_recientes"]] == [2] and antes["limite"] == 7

    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    mundo.sql("DELETE FROM cliente_reciente")
    mundo.sql("UPDATE parametros_sistema SET valor_parametro = '3' WHERE nombre_parametro = 'CLIENTES_RECIENTES_LIMITE'")
    assert client.get("/api/clientes/recientes").get_json()["clientes_recientes"] == []

    r.ejecutar_restauracion(respaldo["id_respaldo"], 1)
    despues = client.get("/api/clientes/recientes").get_json()
    assert despues["limite"] == 7
    assert [c["id_cliente"] for c in despues["clientes_recientes"]] == [2]
    assert despues["clientes_recientes"][0]["fecha_interaccion"] == antes["clientes_recientes"][0]["fecha_interaccion"]
    cn = mundo.conectar()
    cur = cn.cursor()
    cur.execute("SELECT fecha_interaccion FROM cliente_reciente")
    assert cur.fetchone()[0].microsecond == 123456, "DATETIME(6) conserva los microsegundos"
    cn.close()


def test_rf49_los_eventos_posteriores_a_una_restauracion_aparecen_en_cambios_recientes(client, iniciar_sesion, mundo):
    iniciar_sesion(usuario_id=1, rol_id=1)
    respaldo = r.ejecutar_respaldo(r.TIPO_MANUAL, 1)
    respuesta = client.post(f"/api/respaldos/{respaldo['id_respaldo']}/restaurar",
                            json={"confirmacion": "RESTAURAR", "password": CLAVE_ADMIN})
    assert respuesta.status_code == 200
    cambios = client.get("/api/cambios-recientes").get_json()["cambios"]
    assert cambios[0]["tipo"] == "RESTAURACION_RESPALDO" and cambios[0]["modulo"] == "Respaldos"
    assert cambios[0]["usuario"] == "Admin Ficticia"


def test_la_migracion_010_produce_el_mismo_esquema_que_el_instalador(mundo):
    import importlib.util
    especificacion = importlib.util.spec_from_file_location("migrar_prueba", os.path.join(RAIZ, "database", "migrar.py"))
    migrar = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(migrar)

    mundo.sql("DROP TABLE IF EXISTS respaldo", base=BASE_DESTINO)
    cn = mundo.conectar(BASE_DESTINO)
    cur = cn.cursor()
    assert migrar.aplicada(cur, "010") is False
    assert migrar.aplicar(cn, os.path.join(migrar.CARPETA, "010_respaldos.sql")) == 0
    assert migrar.aplicada(cur, "010") is True
    assert migrar.aplicar(cn, os.path.join(migrar.CARPETA, "010_respaldos.sql")) == 1, "repetirla solo informa que ya existe"

    def estructura(base):
        cur.execute(
            "SELECT column_name, column_type, is_nullable, column_default, extra FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = 'respaldo' ORDER BY ordinal_position", (base,))
        columnas = cur.fetchall()
        cur.execute(
            "SELECT index_name, seq_in_index, column_name, non_unique FROM information_schema.statistics "
            "WHERE table_schema = %s AND table_name = 'respaldo' ORDER BY index_name, seq_in_index", (base,))
        return columnas, cur.fetchall()
    assert estructura(BASE_DESTINO) == estructura(BASE_APP)
    assert len(estructura(BASE_APP)[0]) == 15
    cn.close()


def test_la_tabla_de_historial_no_tiene_claves_foraneas(mundo):
    cn = mundo.conectar()
    cur = cn.cursor()
    cur.execute("SELECT COUNT(*) FROM information_schema.table_constraints WHERE table_schema = %s AND table_name = 'respaldo' "
                "AND constraint_type = 'FOREIGN KEY'", (BASE_APP,))
    assert cur.fetchone()[0] == 0, "el historial no puede bloquear ni depender de usuarios restaurados"
    cn.close()


def test_el_historial_sobrevive_a_un_respaldo_cuyo_usuario_ya_no_existe(client, iniciar_sesion, mundo):
    iniciar_sesion(usuario_id=1, rol_id=1)
    r.ejecutar_respaldo(r.TIPO_MANUAL, 2)
    cn = mundo.conectar()
    cur = cn.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    cur.execute("DELETE FROM usuario WHERE id_usuario = 2")
    cn.commit()
    cn.close()
    fila = client.get("/api/respaldos").get_json()["respaldos"][0]
    assert fila["usuario"] is None and fila["estado"] == "EXITOSO"
