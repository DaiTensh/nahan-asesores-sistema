from pathlib import Path

import pytest

import backend.routes.control_horas_routes as control_horas_routes
from tests.conftest import normalize_sql


URL_REGISTROS = "/api/control-horas/registros"
URL_FILTROS = "/api/control-horas/filtros"
ROOT = Path(__file__).resolve().parents[1]


def _handler(capturado, nombre_rol):
    def manejar(sql, params, cursor):
        sql_normalizado = normalize_sql(sql)
        capturado.append((sql_normalizado, params))

        if "FROM usuario u INNER JOIN rol r" in sql_normalizado:
            return [{
                "id_usuario": params[0],
                "estado": "ACTIVO",
                "nombre_rol": nombre_rol,
            }]
        if "u.nombres AS usuario_responsable" in sql_normalizado:
            return [{
                "id_registro": 1,
                "tarea": "Tarea de prueba",
                "descripcion": "",
                "cliente": "Cliente de prueba",
                "fecha": "05-11-2026",
                "inicio": "05-11-2026 09:00:00",
                "inicio_hora": "09:00:00",
                "fin": "10:00:00",
                "duracion_minutos": 60,
                "tarifa_hora": 30000,
                "monto": 30000,
                "usuario_responsable": "Usuario de prueba",
            }]
        if "AS minutos_acumulados" in sql_normalizado:
            return [{
                "minutos_acumulados": 60,
                "monto_acumulado": 30000,
                "minutos_hoy": 0,
                "total_registros": 1,
            }]
        if "FROM cliente c" in sql_normalizado and "AS nombre" in sql_normalizado:
            return [{"nombre": "Cliente de prueba", "minutos": 60, "monto": 30000}]
        if "FROM tarea t" in sql_normalizado and "AS nombre" in sql_normalizado:
            return [{"nombre": "Tarea de prueba", "minutos": 60, "monto": 30000}]
        if "SELECT DISTINCT c.id_cliente" in sql_normalizado:
            return [{"id_cliente": 7, "razon_social": "Cliente de prueba", "rut": "11.111.111-1"}]
        if "SELECT DISTINCT t.id_tarea" in sql_normalizado:
            return [{
                "id_tarea": 3,
                "titulo": "Tarea de prueba",
                "id_cliente": 7,
                "cliente": "Cliente de prueba",
            }]
        if "SELECT DISTINCT u.id_usuario" in sql_normalizado:
            return [{"id_usuario": 1, "nombres": "Usuario de prueba"}]
        return []

    return manejar


@pytest.fixture
def solicitar(client, iniciar_sesion, fake_connection_factory, monkeypatch):
    capturado = []

    def _solicitar(url, query=None, rol_id=1, usuario_id=1, nombre_rol=None):
        nombres_roles = {
            1: "ADMINISTRADOR",
            2: "USUARIO_AREA_JURIDICA",
            3: "USUARIO_AREA_CONTABLE",
        }
        rol = nombre_rol or nombres_roles[rol_id]
        iniciar_sesion(usuario_id=usuario_id, rol_id=rol_id)
        conexion = fake_connection_factory(_handler(capturado, rol))
        monkeypatch.setattr(control_horas_routes, "get_connection", lambda: conexion)
        respuesta = client.get(url, query_string=query or {})
        return respuesta, capturado, conexion

    return _solicitar


@pytest.mark.parametrize(
    "query,error",
    [
        ({"fecha_inicio": "2026-11-01"}, "Debe indicar fecha_inicio y fecha_fin"),
        ({"fecha_fin": "2026-11-01"}, "Debe indicar fecha_inicio y fecha_fin"),
        ({"fecha_inicio": "01-11-2026", "fecha_fin": "2026-11-02"}, "formato AAAA-MM-DD"),
        ({"fecha_inicio": "2026-11-03", "fecha_fin": "2026-11-02"}, "no puede ser posterior"),
        ({"id_cliente": "abc"}, "id_cliente debe ser un ID entero positivo"),
        ({"id_cliente": "0"}, "id_cliente debe ser un ID entero positivo"),
        ({"id_cliente": "-1"}, "id_cliente debe ser un ID entero positivo"),
        ({"id_tarea": "abc"}, "id_tarea debe ser un ID entero positivo"),
        ({"id_tarea": "0"}, "id_tarea debe ser un ID entero positivo"),
        ({"id_tarea": "-1"}, "id_tarea debe ser un ID entero positivo"),
    ],
)
def test_filtros_invalidos_de_registros_responden_400_sin_consultas_de_datos(
    solicitar, query, error
):
    respuesta, consultas, _ = solicitar(URL_REGISTROS, query)

    assert respuesta.status_code == 400
    assert error in respuesta.get_json()["error"]
    assert not any("FROM registro_tiempo rt" in sql for sql, _ in consultas)


def test_filtros_de_fecha_cliente_y_tarea_afectan_listado_y_resumen(solicitar):
    respuesta, consultas, _ = solicitar(
        URL_REGISTROS,
        {
            "fecha_inicio": "2026-11-01",
            "fecha_fin": "2026-11-30",
            "id_cliente": "7",
            "id_tarea": "3",
        },
    )

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert set(datos) == {"registros", "resumen"}
    consultas_datos = [
        (sql, params)
        for sql, params in consultas
        if "FROM registro_tiempo rt" in sql
    ]
    assert len(consultas_datos) == 4
    for sql, params in consultas_datos:
        assert "rt.fecha BETWEEN %s AND %s" in sql
        assert "rt.id_cliente = %s" in sql
        assert "rt.id_tarea = %s" in sql
        assert params == ("2026-11-01", "2026-11-30", 7, 3)


def test_usuario_operativo_no_puede_ampliar_su_alcance_con_id_usuario(solicitar):
    respuesta, consultas, _ = solicitar(
        URL_REGISTROS,
        {"id_usuario": "99"},
        rol_id=2,
        usuario_id=12,
    )

    assert respuesta.status_code == 200
    consultas_datos = [
        (sql, params)
        for sql, params in consultas
        if "FROM registro_tiempo rt" in sql
    ]
    assert len(consultas_datos) == 4
    assert all("rt.id_usuario = %s" in sql for sql, _ in consultas_datos)
    assert all(params == (12,) for _, params in consultas_datos)


def test_catalogos_de_filtros_son_distintos_y_alcanzables_para_administrador(solicitar):
    respuesta, consultas, _ = solicitar(URL_FILTROS)

    assert respuesta.status_code == 200
    assert respuesta.get_json() == {
        "clientes": [{"id_cliente": 7, "razon_social": "Cliente de prueba", "rut": "11.111.111-1"}],
        "tareas": [{
            "id_tarea": 3,
            "titulo": "Tarea de prueba",
            "id_cliente": 7,
            "cliente": "Cliente de prueba",
        }],
        "usuarios": [{"id_usuario": 1, "nombres": "Usuario de prueba"}],
    }
    catalogos = [(sql, params) for sql, params in consultas if "SELECT DISTINCT" in sql]
    assert len(catalogos) == 3
    assert all("rt.hora_fin IS NOT NULL" in sql for sql, _ in catalogos)
    assert all(not params for _, params in catalogos)


@pytest.mark.parametrize("rol_id", [2, 3])
def test_catalogos_operativos_solo_incluyen_datos_propios_y_no_exponen_usuarios(
    solicitar, rol_id
):
    respuesta, consultas, _ = solicitar(
        URL_FILTROS,
        rol_id=rol_id,
        usuario_id=12,
    )

    assert respuesta.status_code == 200
    assert respuesta.get_json()["usuarios"] == []
    catalogos = [(sql, params) for sql, params in consultas if "SELECT DISTINCT" in sql]
    assert len(catalogos) == 2
    assert all("rt.id_usuario = %s" in sql for sql, _ in catalogos)
    assert all(params == (12,) for _, params in catalogos)


def test_catalogos_rechazan_sesiones_sin_rol_permitido(solicitar):
    respuesta, _, _ = solicitar(
        URL_FILTROS,
        nombre_rol="ROL_NO_PERMITIDO",
    )

    assert respuesta.status_code == 403


def test_catalogos_requieren_sesion(client):
    assert client.get(URL_FILTROS).status_code == 401


def test_interfaz_control_horas_expone_filtros_y_resumen_por_alcance():
    html = (ROOT / "frontend/control_horas/control_horas.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/control_horas/control_horas.js").read_text(encoding="utf-8")

    for elemento in (
        'id="formFiltrosHoras"',
        'id="filtroPeriodoRapido"',
        'id="filtroDesde"',
        'id="filtroHasta"',
        'id="filtroCliente"',
        'id="filtroTarea"',
        'id="grupoFiltroUsuario" hidden',
        'id="filtroUsuario"',
        'id="btnLimpiarFiltrosHoras"',
        'id="estadoFiltrosHoras" class="form-help" aria-live="polite"',
        'id="thUsuarioRegistro" hidden>Usuario</th>',
        'id="rotuloHorasHoy"',
        'id="rotuloHorasTotal"',
        'id="rotuloMontoTotal"',
        'id="rotuloRegistros"',
    ):
        assert elemento in html

    assert "Mostrando: mis registros." in js
    assert 'Mostrando: registros de ${nombreUsuario || "todos los usuarios"}.' in js
    assert '· ${nombreUsuario || "todos los usuarios"}' in js
    assert 'parametros.set("fecha_inicio", desde)' in js
    assert 'parametros.set("fecha_fin", hasta)' in js
    assert 'parametros.set("id_cliente", filtroCliente.value)' in js
    assert 'parametros.set("id_tarea", filtroTarea.value)' in js
    assert 'usuarioActual.nombre_rol === "ADMINISTRADOR" && filtroUsuario.value' in js
    assert "No hay registros para los filtros elegidos." in js
    assert "Mostrando ${registros.length} registros." in js


def test_acciones_control_horas_son_solo_administrativas_y_detener_respeta_filtros():
    js = (ROOT / "frontend/control_horas/control_horas.js").read_text(encoding="utf-8")
    bloque_admin = js.split('if (usuarioActual.nombre_rol === "ADMINISTRADOR") {', 1)[1].split(
        "\n  }\n\n  const esAdministrador", 1
    )[0]
    assert 'reportes/reportes.html?tipo=horas' in bloque_admin
    assert bloque_admin.index("Informes de horas") < bloque_admin.index("../tarifas/tarifas.html")

    bloque_detener = js.split("async function detenerTemporizador()", 1)[1].split(
        "\nfunction activarTemporizador", 1
    )[0]
    assert "renderizarResumen(data.resumen)" not in bloque_detener
    assert bloque_detener.index("await cargarRegistros()") < bloque_detener.index(
        "await cargarContexto()"
    )
    assert "formFiltrosHoras.reset()" in js
