import logging
import os
import time
from datetime import timedelta
from urllib.parse import urlsplit

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from backend.routes.auth_routes import auth_bp
from backend.routes.clientes_routes import clientes_blueprint
from backend.routes.control_horas_routes import control_horas_bp
from backend.routes.documentos_routes import documentos_bp
from backend.routes.historial_routes import historial_bp
from backend.routes.notificaciones_routes import notificaciones_bp
from backend.routes.reportes_routes import reportes_blueprint
from backend.routes.respaldos_routes import respaldos_bp
from backend.routes.tarifas_routes import tarifas_bp
from backend.routes.tareas_routes import tareas_bp
from backend.routes.usuarios_routes import usuarios_bp
from backend.routes.busqueda_routes import busqueda_bp
from backend.utils.entorno import entorno_actual, es_entorno_de_desarrollo
from backend.utils.respaldos import restauracion_en_curso


MENSAJES_HTTP = {
    400: "La solicitud no es válida o está incompleta.",
    404: "El recurso solicitado no existe.",
    405: "Método no permitido para este recurso.",
    415: "Tipo de contenido no admitido.",
}

DEFAULT_DEV_SECRET_KEY = "dev-secret-key-change-me"
DEFAULT_DEV_ORIGINS = (
    "http://127.0.0.1:5500",
    "http://localhost:5500",
)


def _bool_env(nombre, default=False):
    valor = os.getenv(nombre)

    if valor is None:
        return default

    return valor.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(nombre):
    valor = os.getenv(nombre, "")
    return [item.strip() for item in valor.split(",") if item.strip()]


def _int_env(nombre, default):
    try:
        return int(os.getenv(nombre, str(default)))
    except (TypeError, ValueError):
        return default


def _configurar_zona_horaria():
    zona_horaria = os.getenv("APP_TIMEZONE", "America/Santiago")
    os.environ["TZ"] = zona_horaria

    if hasattr(time, "tzset"):
        time.tzset()

    return zona_horaria


METODOS_QUE_MODIFICAN = {"POST", "PUT", "PATCH", "DELETE"}


def _origen_permitido(origen, host_solicitud, origenes_permitidos):
    """Defensa en profundidad contra CSRF (además de SameSite).

    Un `Origin` es aceptable si su nombre de host coincide con el de la solicitud o si figura en
    ALLOWED_ORIGINS. Se compara solo el host (sin puerto ni esquema) porque Nginx reenvía `$host`
    sin puerto y la demostración por túnel SSH usa un puerto distinto en el navegador.
    """
    if origen in origenes_permitidos:
        return True
    try:
        host_origen = urlsplit(origen).hostname
    except ValueError:
        return False
    host_propio = (host_solicitud or "").split(":")[0] if not host_solicitud.startswith("[") \
        else host_solicitud.split("]")[0].lstrip("[")
    return bool(host_origen) and host_origen.lower() == host_propio.lower()


def create_app():
    entorno = entorno_actual()
    es_produccion = not es_entorno_de_desarrollo()
    secret_key = os.getenv("SECRET_KEY")

    if es_produccion and (not secret_key or secret_key == DEFAULT_DEV_SECRET_KEY):
        raise RuntimeError(
            "SECRET_KEY debe estar configurada. Sin FLASK_ENV=development explícito "
            "se asume producción y no se permite la clave de desarrollo."
        )
    if es_produccion and len(secret_key) < 32:
        logging.getLogger(__name__).warning(
            "SECRET_KEY tiene menos de 32 caracteres; conviene una clave aleatoria más larga."
        )

    app = Flask(__name__)
    app.config["ENV"] = entorno
    app.config["DEBUG"] = not es_produccion and _bool_env("DEBUG", default=True)
    app.config["SECRET_KEY"] = secret_key or DEFAULT_DEV_SECRET_KEY
    app.config["SESSION_COOKIE_HTTPONLY"] = _bool_env(
        "SESSION_COOKIE_HTTPONLY",
        default=True,
    )
    app.config["SESSION_COOKIE_SAMESITE"] = os.getenv(
        "SESSION_COOKIE_SAMESITE",
        "Lax",
    )
    app.config["SESSION_COOKIE_SECURE"] = _bool_env(
        "SESSION_COOKIE_SECURE",
        default=False,
    )
    if es_produccion and not app.config["SESSION_COOKIE_SECURE"]:
        # Solo avisa: con HTTP puro, `Secure` impediría iniciar sesión (ver docs/deploy_https.md).
        logging.getLogger(__name__).warning(
            "SESSION_COOKIE_SECURE=false en un entorno de producción: la cookie de sesión "
            "puede viajar sin cifrar. Sirva el sistema por HTTPS y active la opción."
        )
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        minutes=_int_env(
            "PERMANENT_SESSION_LIFETIME",
            _int_env("SESSION_LIFETIME_MINUTES", 480),
        )
    )
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True
    # Techo de infraestructura para el cuerpo de cualquier solicitud. El
    # límite funcional de un adjunto (RF54) sigue siendo
    # ADJUNTOS_TAMANO_MAXIMO_MB en parametros_sistema y debe quedar por
    # debajo de este valor; deploy/nginx/nahan.conf usa el mismo techo.
    app.config["MAX_CONTENT_LENGTH"] = _int_env("MAX_CONTENT_LENGTH_MB", 64) * 1024 * 1024
    app.config["APP_TIMEZONE"] = _configurar_zona_horaria()

    @app.before_request
    def bloquear_durante_restauracion():
        # RF60: mientras una restauración reemplaza los datos, el resto de la
        # API no debe leer ni escribir sobre tablas a medio cargar.
        if request.path.startswith("/api/") and restauracion_en_curso():
            respuesta = jsonify({
                "error": "El sistema está en mantenimiento por una restauración de respaldo. "
                         "Intente nuevamente en unos minutos.",
                "codigo": "MANTENIMIENTO",
            })
            respuesta.status_code = 503
            respuesta.headers["Retry-After"] = "60"
            return respuesta

    @app.before_request
    def comprobar_origen_de_escritura():
        # CSRF: una escritura iniciada desde otro sitio se rechaza aunque lleve la cookie.
        # Sin cabecera Origin (clientes no navegador, pruebas) no hay nada que comprobar.
        if not request.path.startswith("/api/") or request.method not in METODOS_QUE_MODIFICAN:
            return None
        if not _bool_env("CSRF_COMPROBAR_ORIGEN", default=True):
            return None
        origen = request.headers.get("Origin")
        if origen is None:
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                return jsonify({"error": "Solicitud de origen no permitido."}), 403
            return None
        permitidos = _csv_env("ALLOWED_ORIGINS") or ([] if es_produccion else list(DEFAULT_DEV_ORIGINS))
        if not _origen_permitido(origen, request.host, permitidos):
            return jsonify({"error": "Solicitud de origen no permitido."}), 403
        return None

    @app.before_request
    def validar_cuerpo_json():
        if not request.path.startswith("/api/") or not request.is_json:
            return None
        if not request.get_data(cache=True):
            # Content-Type JSON sin cuerpo (por ejemplo, un POST de acción sin datos): no hay nada que validar.
            return None
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict):
            return jsonify({"error": "El cuerpo debe ser un objeto JSON válido"}), 400

        campos_texto = {
            "email", "password", "token", "nombres", "rut", "razon_social",
            "telefono", "direccion", "titulo", "descripcion", "prioridad", "estado",
            "nuevo_estado", "fecha_inicio", "fecha_vencimiento", "nombre_documento", "tipo_documento",
            "ubicacion_referencia", "observaciones", "texto",
        }
        largos_maximos = {
            "nombres": 100, "email": 150, "rut": 20, "razon_social": 200,
            "telefono": 20, "direccion": 255, "titulo": 200,
            "nombre_documento": 200, "tipo_documento": 60, "ubicacion_referencia": 255,
        }
        for campo, valor in datos.items():
            if campo in campos_texto and valor is not None and not isinstance(valor, str):
                return jsonify({"error": f"{campo} debe ser texto"}), 400
            if campo in largos_maximos and isinstance(valor, str) and len(valor) > largos_maximos[campo]:
                return jsonify({"error": f"{campo} supera el máximo de {largos_maximos[campo]} caracteres"}), 400
            if campo in {"areas", "ids_tarea"} and valor is not None:
                if not isinstance(valor, list) or any(
                    isinstance(item, bool) or not str(item).isdecimal() or int(item) < 1
                    for item in valor
                ):
                    return jsonify({"error": f"{campo} debe ser una lista de IDs enteros positivos"}), 400
            if campo.startswith("id_") and valor not in (None, ""):
                if campo == "id_area" and valor == "AMBAS":
                    continue
                if isinstance(valor, bool) or not str(valor).isdecimal() or int(valor) < 1:
                    return jsonify({"error": f"{campo} debe ser un ID entero positivo"}), 400
        password = datos.get("password")
        if password and len(password.encode("utf-8")) > 72:
            return jsonify({"error": "La contraseña no puede superar 72 bytes UTF-8"}), 400

    @app.errorhandler(RequestEntityTooLarge)
    def solicitud_demasiado_grande(error):
        limite_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return jsonify({
            "error": f"La solicitud supera el tamaño máximo admitido por el servidor ({limite_mb} MB)"
        }), 413

    @app.errorhandler(HTTPException)
    def error_http(error):
        respuesta = error.get_response()
        if request.path.startswith("/api/"):
            # Werkzeug redacta estos mensajes en inglés; la API responde en español.
            descripcion = MENSAJES_HTTP.get(error.code, error.description)
            respuesta.data = app.json.dumps({"error": descripcion})
            respuesta.content_type = "application/json"
        return respuesta

    logging.basicConfig(
        level=logging.DEBUG if app.config["DEBUG"] else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    origenes = _csv_env("ALLOWED_ORIGINS")
    if not origenes and not es_produccion:
        origenes = list(DEFAULT_DEV_ORIGINS)

    if origenes:
        CORS(
            app,
            origins=origenes,
            supports_credentials=True,
            expose_headers=["Content-Disposition"],
        )

    if _bool_env("TRUST_PROXY", default=False):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_prefix=1,
        )

    app.register_blueprint(usuarios_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api")
    app.register_blueprint(tareas_bp, url_prefix="/api")
    app.register_blueprint(clientes_blueprint, url_prefix="/api")
    app.register_blueprint(control_horas_bp, url_prefix="/api")
    app.register_blueprint(documentos_bp, url_prefix="/api")
    app.register_blueprint(reportes_blueprint, url_prefix="/api")
    app.register_blueprint(historial_bp, url_prefix="/api")
    app.register_blueprint(notificaciones_bp, url_prefix="/api")
    app.register_blueprint(busqueda_bp, url_prefix="/api")
    app.register_blueprint(respaldos_bp, url_prefix="/api")
    app.register_blueprint(tarifas_bp, url_prefix="/api")

    @app.route("/")
    def home():
        return {"message": "API Nahan Asesores funcionando correctamente"}

    return app


app = create_app()


if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    port = _int_env("FLASK_RUN_PORT", 5000)
    app.run(host=host, port=port, debug=app.config["DEBUG"])
