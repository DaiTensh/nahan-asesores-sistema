import logging
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def get_connection():
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME")
        )
    except mysql.connector.Error as error:
        logger.error("Error de conexión a MySQL: %s", error)
        return None
