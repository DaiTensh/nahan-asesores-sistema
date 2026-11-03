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


def test_los_recursos_estaticos_se_revalidan_en_lugar_de_cachearse_dias():
    """Con «expires 7d» un usuario conservaba JS y CSS viejos hasta una semana después de un despliegue."""
    conf = _conf()
    assert "expires 7d" not in conf and 'add_header Cache-Control "no-cache";' in conf
