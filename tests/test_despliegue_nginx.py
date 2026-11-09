"""Plantilla de Nginx (deploy/nginx/nahan.conf): cabeceras de seguridad y rutas clave."""
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _conf():
    with open(os.path.join(RAIZ, "deploy", "nginx", "nahan.conf"), encoding="utf-8") as archivo:
        return archivo.read()


def test_las_cabeceras_de_seguridad_estan_en_el_servidor_y_en_los_recursos_estaticos():
    conf = _conf()
    for cabecera in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"):
        assert len(re.findall(rf'add_header {cabecera} ', conf)) == 2, cabecera
    assert "server_tokens off;" in conf
    assert "Strict-Transport-Security" not in conf, "sin HTTPS no se debe enviar HSTS"


def test_la_api_y_los_adjuntos_conservan_sus_limites():
    conf = _conf()
    assert "client_max_body_size 15m;" in conf and "client_max_body_size 64m;" in conf
    assert "proxy_pass http://127.0.0.1:8000/api/;" in conf
    assert "return 302 /auth/login.html;" in conf


def test_las_redirecciones_son_relativas_para_conservar_el_puerto_del_tunel_ssh():
    """La demostración se abre por un túnel (localhost:8080): con una redirección absoluta Nginx omite ese puerto."""
    conf = _conf()
    servidor = re.sub(r"^\s*#.*$", "", conf[conf.index("server {"):], flags=re.MULTILINE)
    assert "absolute_redirect off;" in servidor
    antes = servidor[:servidor.index("absolute_redirect off;")]
    assert antes.count("{") - antes.count("}") == 1, \
        "la directiva va a nivel de «server» para cubrir también las páginas inexistentes"


def test_los_recursos_estaticos_se_revalidan_en_lugar_de_cachearse_dias():
    """Con «expires 7d» un usuario conservaba JS y CSS viejos hasta una semana después de un despliegue."""
    conf = _conf()
    assert "expires 7d" not in conf and 'add_header Cache-Control "no-cache";' in conf


def test_nginx_espera_a_gunicorn_tanto_como_este_admite_para_los_respaldos():
    """Con el valor por defecto de Nginx (60 s) un respaldo largo daba error en pantalla aunque terminara."""
    with open(os.path.join(RAIZ, "deploy", "systemd", "nahan.service"), encoding="utf-8") as archivo:
        gunicorn = int(re.search(r"--timeout (\d+)", archivo.read()).group(1))
    conf = _conf()
    bloque_api = conf[conf.index("location /api/ {"):conf.index("location = / {")]
    espera = int(re.search(r"proxy_read_timeout (\d+)s;", bloque_api).group(1))
    assert espera >= gunicorn


def test_el_inicio_de_sesion_tiene_un_limite_de_solicitudes_por_ip():
    conf = _conf()
    assert re.search(r"limit_req_zone \$binary_remote_addr zone=nahan_login:\d+m rate=\d+r/m;", conf)
    bloque = conf[conf.index("location = /api/login"):]
    bloque = bloque[:bloque.index("}")]
    assert "limit_req zone=nahan_login" in bloque and "proxy_pass http://127.0.0.1:8000/api/login;" in bloque
    assert conf.index("limit_req_zone") < conf.index("server {"), "la zona va fuera del bloque server (contexto http)"


def _ubicaciones(texto):
    return set(re.findall(r"location\s+((?:[=~*]+\s+)?\S+)\s*\{", texto))


def test_la_plantilla_https_tiene_las_mismas_rutas_que_la_vigente():
    """Si se cambia una «location» de nahan.conf hay que cambiarla en la plantilla HTTPS, y al revés."""
    with open(os.path.join(RAIZ, "deploy", "nginx", "nahan-https.conf.example"), encoding="utf-8") as archivo:
        https = archivo.read()
    assert _ubicaciones(https) - {"/.well-known/acme-challenge/"} == _ubicaciones(_conf())
    assert "return 301 https://$host$request_uri;" in https
    assert "Strict-Transport-Security" in https and "ssl_protocols TLSv1.2 TLSv1.3;" in https
    assert "DOMINIO" in https, "es una plantilla: el dominio se reemplaza al activarla"
