"""Matriz de permisos por rol (cierre técnico).

Complementa `test_todas_las_api_privadas_rechazan_anonimos`: recorre cada ruta
`/api/` y comprueba, según el decorador real del código, que

* una ruta exclusiva del administrador responde 403 a los dos roles de área;
* ninguna ruta privada queda sin decorador de autenticación.

La lista de rutas se deriva del propio código (AST), de modo que una ruta nueva
sin protección hace fallar la prueba en vez de pasar inadvertida.
"""
import ast
import glob
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLICAS = {
    "auth.login", "auth.logout", "auth.solicitar_restablecimiento",
    "auth.verificar_token_restablecimiento", "auth.confirmar_restablecimiento",
}


def _decoradores_por_funcion():
    mapa = {}
    for ruta in glob.glob(os.path.join(RAIZ, "backend", "routes", "*.py")):
        arbol = ast.parse(open(ruta, encoding="utf-8").read())
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.FunctionDef):
                nombres = []
                for dec in nodo.decorator_list:
                    if isinstance(dec, ast.Call):
                        args = [ast.unparse(a) if hasattr(ast, "unparse") else ast.dump(a) for a in dec.args]
                        nombres.append((getattr(dec.func, "id", getattr(dec.func, "attr", "")), tuple(args)))
                    else:
                        nombres.append((getattr(dec, "id", getattr(dec, "attr", "")), ()))
                mapa[nodo.name] = nombres
    return mapa


def _rutas_api(app):
    decs = _decoradores_por_funcion()
    for regla in app.url_map.iter_rules():
        if not regla.rule.startswith("/api/") or regla.endpoint in PUBLICAS:
            continue
        funcion = regla.endpoint.split(".")[-1]
        ruta = re.sub(r"<(?:int:)?[^>]+>", "1", regla.rule)
        for metodo in sorted(regla.methods - {"OPTIONS", "HEAD"}):
            yield regla.endpoint, funcion, ruta, metodo, decs.get(funcion, [])


def _es_solo_admin(decoradores):
    return any(n == "roles_required" and a == ("ROL_ADMINISTRADOR",) for n, a in decoradores)


def _tiene_proteccion(decoradores):
    return any(n in {"login_required", "roles_required"} for n, _ in decoradores)


def test_toda_ruta_privada_declara_autenticacion(client):
    sin_proteger = [
        (ep, m, r) for ep, f, r, m, d in _rutas_api(client.application) if not _tiene_proteccion(d)
    ]
    assert sin_proteger == []


def test_hay_rutas_exclusivas_de_administrador(client):
    assert sum(1 for *_, d in _rutas_api(client.application) if _es_solo_admin(d)) >= 20


@pytest.mark.parametrize("rol_id", [2, 3])
def test_rutas_de_administrador_rechazan_roles_de_area(client, iniciar_sesion, rol_id):
    iniciar_sesion(usuario_id=7, rol_id=rol_id, area_id=1)
    permitidas = []
    for ep, f, ruta, metodo, d in _rutas_api(client.application):
        if not _es_solo_admin(d):
            continue
        r = client.open(ruta, method=metodo, json={} if metodo != "GET" else None)
        if r.status_code != 403:
            permitidas.append((ep, metodo, r.status_code))
    assert permitidas == []
