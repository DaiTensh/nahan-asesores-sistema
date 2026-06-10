from flask import Flask
from flask_cors import CORS
from backend.routes.usuarios_routes import usuarios_bp
from backend.routes.auth_routes import auth_bp
from backend.routes.tareas_routes import tareas_bp
from backend.routes.clientes_routes import clientes_blueprint

app = Flask(__name__)
CORS(app)

app.register_blueprint(usuarios_bp, url_prefix="/api")
app.register_blueprint(auth_bp, url_prefix="/api")
app.register_blueprint(tareas_bp, url_prefix="/api")
app.register_blueprint(clientes_blueprint, url_prefix="/api")

@app.route("/")
def home():
    return {"message": "API Nahan Asesores funcionando correctamente"}

if __name__ == "__main__":
    app.run(debug=True, port=5000)