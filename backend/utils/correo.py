import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def _configuracion():
    usuario = os.getenv("SMTP_USER", "").strip()

    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "puerto": _puerto(),
        "usuario": usuario,
        "password": os.getenv("SMTP_PASSWORD", ""),
        "remitente": os.getenv("SMTP_FROM", "").strip() or usuario,
        "nombre_remitente": os.getenv("SMTP_FROM_NAME", "Nahan Asesores").strip()
    }


def _puerto():
    try:
        return int(os.getenv("SMTP_PORT", "587"))
    except (TypeError, ValueError):
        return 587


def smtp_configurado():
    """El envío real requiere servidor, usuario y contraseña.

    Mientras no exista la cuenta de correo del proyecto, el sistema funciona
    igual: el enlace queda registrado en el log de la aplicación en lugar de
    salir por correo. Así el flujo completo se puede probar y demostrar sin
    depender de un servicio externo.
    """
    configuracion = _configuracion()

    return bool(
        configuracion["host"]
        and configuracion["usuario"]
        and configuracion["password"]
    )


def enviar_correo(destinatario, asunto, cuerpo):
    """Envía un correo de texto plano.

    Devuelve True si salió por SMTP y False si quedó registrado en el log
    porque el servidor no está configurado o el envío falló. En ningún caso
    lanza una excepción: el flujo que lo invoca no debe interrumpirse ni
    revelar al usuario si el correo pudo entregarse.
    """
    if not smtp_configurado():
        if os.getenv("FLASK_ENV", "development").lower() == "production":
            logger.warning("SMTP no configurado; el correo no se envió.")
            return False
        logger.warning(
            "SMTP no configurado. El correo no se envió y su contenido queda "
            "registrado aquí para desarrollo.\nPara: %s\nAsunto: %s\n%s",
            destinatario, asunto, cuerpo
        )
        return False

    configuracion = _configuracion()

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = f"{configuracion['nombre_remitente']} <{configuracion['remitente']}>"
    mensaje["To"] = destinatario
    mensaje.set_content(cuerpo)

    contexto = ssl.create_default_context()

    try:
        if configuracion["puerto"] == 465:
            with smtplib.SMTP_SSL(configuracion["host"], configuracion["puerto"],
                                  context=contexto, timeout=15) as servidor:
                servidor.login(configuracion["usuario"], configuracion["password"])
                servidor.send_message(mensaje)
        else:
            # 587 con STARTTLS. El puerto 25 está bloqueado en la instancia EC2.
            with smtplib.SMTP(configuracion["host"], configuracion["puerto"], timeout=15) as servidor:
                servidor.ehlo()
                servidor.starttls(context=contexto)
                servidor.ehlo()
                servidor.login(configuracion["usuario"], configuracion["password"])
                servidor.send_message(mensaje)

    except Exception:
        logger.exception("No se pudo enviar el correo a %s", destinatario)
        return False

    logger.info("Correo enviado a %s", destinatario)
    return True


def cuerpo_restablecimiento(nombres, enlace, minutos_vigencia):
    return (
        f"Hola {nombres}:\n\n"
        "Recibimos una solicitud para restablecer la contraseña de tu cuenta en el "
        "Sistema de Gestión Interna de Nahan Asesores.\n\n"
        f"Para definir una contraseña nueva, abre el siguiente enlace:\n\n{enlace}\n\n"
        f"El enlace vence en {minutos_vigencia} minutos y solo se puede usar una vez.\n\n"
        "Si no solicitaste el cambio, ignora este mensaje: tu contraseña actual sigue "
        "vigente y el enlace caducará solo.\n\n"
        "Sistema de Gestión Interna — Nahan Asesores"
    )
