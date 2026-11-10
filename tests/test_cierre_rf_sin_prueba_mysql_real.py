# -*- coding: utf-8 -*-
"""Pruebas específicas (MySQL real desechable, datos ficticios) para RF que solo tenían evidencia de UI.

Cada prueba ejerce la API real contra el esquema real de `database/nahan_asesores.sql`:
RF02, RF04, RF05, RF06, RF07, RF08, RF09, RF11, RF20, RF61, RF31, RF32, RF34 y RF71-RF73.
Nunca usa el puerto 3306 ni las variables DB_* del desarrollador.
"""
import os

import pytest

from tests.mysql_desechable import (
    BASE_APP, CLAVE_APP, USUARIO_APP, MySQLDesechable, herramientas_disponibles, sembrar_datos_ficticios,
)

pytestmark = pytest.mark.skipif(
    not herramientas_disponibles() or os.getenv("NAHAN_TEST_SIN_MYSQL") == "1",
    reason="requiere mysqld y mysqldump instalados (o NAHAN_TEST_SIN_MYSQL=1)",
)


@pytest.fixture(scope="module")
def servidor():
    s = MySQLDesechable().iniciar()
    yield s
    s.detener()


@pytest.fixture
def mundo(servidor, monkeypatch):
    root = servidor.conectar()
    c = root.cursor()
    c.execute(f"DROP DATABASE IF EXISTS {BASE_APP}")
    c.execute(f"CREATE DATABASE {BASE_APP} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    root.close()
    servidor.cargar_esquema()
    cn = servidor.conectar(base=BASE_APP)
    sembrar_datos_ficticios(cn)
    cn.cursor().execute(
        "INSERT INTO cliente_area (id_cliente, id_area, fecha_asignacion) VALUES (1, 1, NOW()), (2, 2, NOW())")
    cn.commit()
    cn.close()
    assert servidor.puerto != 3306
    for k, v in {"DB_HOST": "127.0.0.1", "DB_PORT": str(servidor.puerto), "DB_USER": USUARIO_APP,
                 "DB_PASSWORD": CLAVE_APP, "DB_NAME": BASE_APP}.items():
        monkeypatch.setenv(k, v)

    class Mundo:
        def sql(self, sentencia, parametros=None, filas=False):
            conexion = servidor.conectar(base=BASE_APP)
            cur = conexion.cursor(dictionary=True)
            cur.execute(sentencia, parametros)
            resultado = cur.fetchall() if filas else None
            conexion.commit()
            conexion.close()
            return resultado

    return Mundo()


@pytest.fixture
def admin(client, iniciar_sesion):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3, nombre="Admin Ficticia")
    return client


# ----------------------------------------------------------------- Clientes
def test_rf02_modificar_cliente_persiste_y_deja_historial(admin, mundo):
    r = admin.put("/api/clientes/1", json={
        "razon_social": "Razón Nueva Ltda.", "email": "nuevo@ejemplo.invalid",
        "telefono": "+56 9 1111 2222", "direccion": "Calle Nueva 456", "areas": [1]})
    assert r.status_code == 200, r.get_json()
    fila = mundo.sql("SELECT rut, razon_social, telefono, direccion FROM cliente WHERE id_cliente = 1", filas=True)[0]
    assert fila == {"rut": "11.111.111-1", "razon_social": "Razón Nueva Ltda.",
                    "telefono": "+56 9 1111 2222", "direccion": "Calle Nueva 456"}  # el RUT no cambia
    assert mundo.sql("SELECT COUNT(*) n FROM auditoria WHERE tabla_afectada = 'cliente' AND id_registro = 1",
                     filas=True)[0]["n"] >= 1
    assert admin.put("/api/clientes/1", json={"razon_social": "", "areas": [1]}).status_code == 400
    assert admin.put("/api/clientes/1", json={"razon_social": "X", "areas": []}).status_code == 400
    assert admin.put("/api/clientes/999", json={"razon_social": "X", "areas": [1]}).status_code == 404


def test_rf04_y_rf61_ficha_y_resumen_consolidan_datos_del_cliente(admin, mundo):
    ficha = admin.get("/api/clientes/1/ficha").get_json()
    assert ficha["rut"] == "11.111.111-1" and ficha["areas_nombres"] == "JURIDICA"
    assert ficha["tareas_activas"] == 1 and ficha["tareas"][0]["estado"] == "PENDIENTE"
    assert admin.get("/api/clientes/999/ficha").status_code == 404
    resumen = admin.get("/api/clientes/resumen").get_json()
    assert (resumen["total_clientes"], resumen["clientes_activos"], resumen["clientes_inactivos"]) == (2, 2, 0)
    mundo.sql("UPDATE cliente SET estado = 'INACTIVO' WHERE id_cliente = 2")
    resumen = admin.get("/api/clientes/resumen").get_json()
    assert (resumen["clientes_activos"], resumen["clientes_inactivos"]) == (1, 1)


def test_rf05_busqueda_por_texto(admin, mundo):
    nombres = lambda q: [c["razon_social"] for c in admin.get("/api/clientes/filtrar", query_string=q).get_json()]
    assert nombres({"buscar": "Dos"}) == ["Cliente Dos"]
    assert nombres({"buscar": "22.222.222"}) == ["Cliente Dos"]
    assert nombres({"buscar": "no-existe-xyz"}) == []


def test_rf06_filtro_por_area(admin, mundo):
    ids = lambda a: [c["id_cliente"] for c in admin.get("/api/clientes/filtrar", query_string={"id_area": a}).get_json()]
    assert ids(1) == [1] and ids(2) == [2]


def test_rf11_listado_general_pagina_de_a_siete(admin, mundo):
    for i in range(3, 10):
        mundo.sql("INSERT INTO cliente (rut, razon_social) VALUES (%s, %s)", (f"{i}0.000.000-0", f"Cliente {i:02d}"))
    p1 = admin.get("/api/clientes/listado").get_json()["clientes"]
    p2 = admin.get("/api/clientes/listado", query_string={"pagina": 2}).get_json()["clientes"]
    assert len(p1) == 7 and len(p2) == 2  # 9 clientes en total
    assert {c["id_cliente"] for c in p1}.isdisjoint({c["id_cliente"] for c in p2})
    assert admin.get("/api/clientes/listado", query_string={"pagina": 0}).status_code == 400
    assert admin.get("/api/clientes/listado", query_string={"pagina": "x"}).status_code == 400


def test_rf07_y_rf08_referencias_de_documentos(admin, mundo):
    cuerpo = {"nombre_documento": "Escritura", "tipo_documento": "Legal", "ubicacion_referencia": "Archivador 3"}
    assert admin.post("/api/clientes/1/documentos", json=cuerpo).status_code == 201
    assert admin.post("/api/clientes/1/documentos", json=cuerpo).status_code in (400, 409)  # duplicada
    assert admin.post("/api/clientes/1/documentos", json={**cuerpo, "ubicacion_referencia": ""}).status_code == 400
    assert admin.post("/api/clientes/999/documentos", json=cuerpo).status_code == 404
    docs = admin.get("/api/clientes/1/ficha").get_json()["documentos"]
    assert [d["nombre_documento"] for d in docs] == ["Escritura"]  # RF08: solo referencias, sin archivo


def test_rf09_observaciones_internas_guardan_autor_y_texto(admin, mundo):
    assert admin.post("/api/clientes/1/observaciones", json={"texto": "Llamar el lunes"}).status_code == 201
    assert admin.post("/api/clientes/1/observaciones", json={"texto": "   "}).status_code == 400
    obs = admin.get("/api/clientes/1/observaciones").get_json()["observaciones"]
    assert obs[0]["texto"] == "Llamar el lunes" and obs[0]["registrado_por"] == "Admin Ficticia"
    assert len(obs) == 2  # la sembrada y la nueva, la más reciente primero


# -------------------------------------------------------------------- Tareas
def test_rf20_prioridad_de_tarea(admin, mundo):
    assert admin.put("/api/tareas/1/prioridad", json={"prioridad": "URGENTE"}).status_code == 200
    assert mundo.sql("SELECT prioridad FROM tarea WHERE id_tarea = 1", filas=True)[0]["prioridad"] == "URGENTE"
    assert admin.put("/api/tareas/1/prioridad", json={"prioridad": "INVENTADA"}).status_code == 400
    assert mundo.sql("SELECT prioridad FROM tarea WHERE id_tarea = 1", filas=True)[0]["prioridad"] == "URGENTE"
    assert admin.put("/api/tareas/999/prioridad", json={"prioridad": "ALTA"}).status_code == 404


# ------------------------------------------------------------------ Reportes
PERIODO = {"fecha_inicio": "2000-01-01", "fecha_fin": "2100-01-01"}


def test_rf31_y_rf32_reportes_de_tareas_por_cliente_y_por_responsable(admin, mundo):
    r = admin.get("/api/reportes/tareas-por-cliente", query_string={"id_cliente": 1, **PERIODO})
    assert r.status_code == 200, r.get_json()
    assert "Renta" in r.get_data(as_text=True)
    assert admin.get("/api/reportes/tareas-por-cliente", query_string={"id_cliente": 1}).status_code == 400
    r = admin.get("/api/reportes/tareas-por-responsable", query_string={"id_responsable": 1, **PERIODO})
    assert r.status_code == 200 and "Renta" in r.get_data(as_text=True)
    assert admin.get("/api/reportes/tareas-por-responsable", query_string=PERIODO).status_code == 400


def test_rf34_exportar_reporte_a_pdf(admin, mundo):
    r = admin.get("/api/reportes/tareas-por-cliente", query_string={"id_cliente": 1, **PERIODO})
    id_reporte = r.get_json()["id_reporte"]
    pdf = admin.get(f"/api/reportes/{id_reporte}/pdf")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf" and pdf.data.startswith(b"%PDF")
    assert admin.get("/api/reportes/99999/pdf").status_code == 404


# --------------------------------------------------------------------- Horas
def _retroceder_registro_abierto(mundo, minutos):
    mundo.sql("UPDATE registro_tiempo SET fecha = DATE(NOW() - INTERVAL %s MINUTE), "
              "hora_inicio = TIME(NOW() - INTERVAL %s MINUTE) WHERE hora_fin IS NULL", (minutos, minutos))


def test_rf71_rf72_rf73_temporizador_registro_por_usuario_y_totales(admin, mundo):
    assert admin.post("/api/control-horas/iniciar", json={"id_tarea": 1}).status_code == 201
    # RF71: no se puede tener dos temporizadores a la vez
    assert admin.post("/api/control-horas/iniciar", json={"id_tarea": 1}).status_code in (400, 409)
    _retroceder_registro_abierto(mundo, 90)
    r = admin.post("/api/control-horas/detener")
    assert r.status_code == 200
    registro = r.get_json()["registro"]
    assert round(registro["duracion_minutos"]) == 90 and registro["tarifa_hora"] == 30000.0
    assert round(registro["monto"]) == 45000  # 1,5 h × $30.000
    assert admin.post("/api/control-horas/detener").status_code == 404  # ya no hay temporizador
    # RF72: el historial es del usuario y trae su nombre
    lista = admin.get("/api/control-horas/registros").get_json()
    assert [x["usuario_responsable"] for x in lista["registros"]] == ["Admin Ficticia"]
    # RF73: totales acumulados por tarea y por cliente
    resumen = lista["resumen"]
    assert round(resumen["minutos_acumulados"]) == 90 and round(resumen["monto_acumulado"]) == 45000
    assert round(resumen["totales_cliente"][0]["minutos"]) == 90
    assert round(resumen["totales_tarea"][0]["minutos"]) == 90


def test_rf72_un_usuario_no_ve_las_horas_de_otro(client, iniciar_sesion, mundo):
    iniciar_sesion(usuario_id=1, rol_id=1, area_id=3, nombre="Admin Ficticia")
    client.post("/api/control-horas/iniciar", json={"id_tarea": 1})
    client.post("/api/control-horas/detener")
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1, nombre="Usuaria Jurídica")
    assert client.get("/api/control-horas/registros").get_json()["registros"] == []


# ------------------------------------------------------ Aislamiento entre áreas
def test_aislamiento_entre_areas_tareas_aisladas_y_clientes_compartidos(client, iniciar_sesion, mundo):
    """Describe el comportamiento ACTUAL (hallazgo B-18): las tareas y las horas de otra área no son accesibles,
    pero cualquier usuario operativo puede leer y modificar clientes de otra área. Si el cliente decide aislar
    también los clientes, las dos últimas aserciones son las que deben cambiar."""
    mundo.sql("INSERT INTO usuario (id_rol, id_area, nombres, email, password_hash) "
              "VALUES (3, 2, 'Contable Ficticio', 'c@ejemplo.invalid', 'x')")
    mundo.sql("INSERT INTO tarea (id_cliente, id_area, id_responsable, id_creador, titulo, fecha_vencimiento) "
              "VALUES (2, 2, 3, 1, 'Tarea contable', '2030-01-01')")
    iniciar_sesion(usuario_id=2, rol_id=2, area_id=1, nombre="Usuaria Jurídica")  # área Jurídica
    # Aislado: tareas ajenas
    assert client.get("/api/tareas/2").status_code == 403
    assert client.get("/api/tareas/2/documentos").status_code == 403
    assert client.put("/api/tareas/2/prioridad", json={"prioridad": "ALTA"}).status_code == 403
    assert client.put("/api/tareas/2/estado", json={"estado": "EN_PROCESO"}).status_code == 403
    assert client.post("/api/control-horas/iniciar", json={"id_tarea": 2}).status_code == 404
    assert client.get("/api/tareas/pendientes").get_json() == []
    # Compartido (comportamiento actual, a decidir): clientes de otra área
    assert client.get("/api/clientes/2/ficha").status_code == 200
    assert client.put("/api/clientes/2", json={"razon_social": "Modificado por otra área", "areas": [2]}).status_code == 200
