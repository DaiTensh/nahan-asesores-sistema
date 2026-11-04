import logging
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def _segundos_de_conexion():
    try:
        return max(1, int(os.getenv("DB_CONNECT_TIMEOUT", "10")))
    except ValueError:
        return 10


def get_connection():
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            # Sin esto una base que no responde deja la solicitud (y el worker) esperando
            # el tiempo del sistema operativo (AUD-016).
            connection_timeout=_segundos_de_conexion(),
        )
    except mysql.connector.Error as error:
        logger.error("Error de conexión a MySQL: %s", error)
        return None
