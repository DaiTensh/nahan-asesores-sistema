from flask import Flask
from flask_cors import CORS
from routes.usuarios_routes import usuarios_bp
from routes.clientes_routes import clientes_blueprint

app = Flask(__name__)
CORS(app)

app.register_blueprint(usuarios_bp, url_prefix="/api")

@app.route("/")
def home():
    return {"message": "API Nahan Asesores funcionando correctamente"}

if __name__ == "__main__":
    app.run(debug=True, port=5000)