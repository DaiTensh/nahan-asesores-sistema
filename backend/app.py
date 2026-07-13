import os
from datetime import timedelta

from flask import Flask
from flask_cors import CORS
from backend.routes.usuarios_routes import usuarios_bp
from backend.routes.auth_routes import auth_bp
from backend.routes.tareas_routes import tareas_bp
from backend.routes.clientes_routes import clientes_blueprint
from backend.routes.control_horas_routes import control_horas_bp

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
    minutes=int(os.getenv("SESSION_LIFETIME_MINUTES", "480"))
)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

CORS(
    app,
    origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    supports_credentials=True,
)

app.register_blueprint(usuarios_bp, url_prefix="/api")
app.register_blueprint(auth_bp, url_prefix="/api")
app.register_blueprint(tareas_bp, url_prefix="/api")
app.register_blueprint(clientes_blueprint, url_prefix="/api")
app.register_blueprint(control_horas_bp, url_prefix="/api")

@app.route("/")
def home():
    return {"message": "API Nahan Asesores funcionando correctamente"}

if __name__ == "__main__":
    app.run(debug=True, port=5000)
