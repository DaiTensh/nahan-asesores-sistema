from flask import Flask
from flask_cors import CORS
from backend.routes.usuarios_routes import usuarios_bp
from backend.routes.auth_routes import auth_bp

app = Flask(__name__)
CORS(app)

app.register_blueprint(usuarios_bp, url_prefix="/api")
app.register_blueprint(auth_bp, url_prefix="/api")

@app.route("/")
def home():
    return {"message": "API Nahan Asesores funcionando correctamente"}

if __name__ == "__main__":
    app.run(debug=True, port=5000)