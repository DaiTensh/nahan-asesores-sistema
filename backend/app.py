import logging
import os
import time
from datetime import timedelta

from flask import Flask
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from backend.routes.auth_routes import auth_bp
from backend.routes.clientes_routes import clientes_blueprint
from backend.routes.control_horas_routes import control_horas_bp
from backend.routes.documentos_routes import documentos_bp
from backend.routes.tareas_routes import tareas_bp
from backend.routes.usuarios_routes import usuarios_bp


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


def create_app():
    entorno = os.getenv("FLASK_ENV", "development").strip().lower()
    es_produccion = entorno == "production"
    secret_key = os.getenv("SECRET_KEY")

    if es_produccion and not secret_key:
        raise RuntimeError("SECRET_KEY debe estar configurada en producción.")

    app = Flask(__name__)
    app.config["ENV"] = entorno
    app.config["DEBUG"] = _bool_env("DEBUG", default=not es_produccion)
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
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        minutes=_int_env(
            "PERMANENT_SESSION_LIFETIME",
            _int_env("SESSION_LIFETIME_MINUTES", 480),
        )
    )
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True
    app.config["APP_TIMEZONE"] = _configurar_zona_horaria()

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

    @app.route("/")
    def home():
        return {"message": "API Nahan Asesores funcionando correctamente"}

    return app


app = create_app()


if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    port = _int_env("FLASK_RUN_PORT", 5000)
    app.run(host=host, port=port, debug=app.config["DEBUG"])
