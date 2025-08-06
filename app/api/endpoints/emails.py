import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from email.message import EmailMessage
import aiosmtplib
from sqlmodel import Session

from app.api import router
from app.api.endpoints.token import verify_token
from app.config.database import get_db
from app.models.wep_user_model import WepUserModel

# Cargar variables de entorno
load_dotenv()

class EmailRequest(BaseModel):
    client_email: str  # Correo del cliente (para reply-to)
    subject: str       # Asunto del mensaje
    message: str       # Contenido del mensaje

# Configuración SMTP
SMTP_CONFIG = {
    "server": os.getenv("SMTP_SERVER"),
    "port": int(os.getenv("SMTP_PORT")),
    "username": os.getenv("SMTP_USERNAME"),  # correo (receptor)
    "password": os.getenv("SMTP_PASSWORD"),
    "receiver_email": os.getenv("RECEIVER_EMAIL"),  # correo (puede ser igual a username)
    "from_name": os.getenv("FROM_NAME", "Sitio Web")  # Nombre que aparece como remitente
}

router = APIRouter()

@router.post("/")
async def send_contact_email(email_data: EmailRequest,
        current_user: WepUserModel = Depends(verify_token),
        db: Session = Depends(get_db)):
    try:
        msg = EmailMessage()
        # De: Nombre Sitio <tu_correo@dominio.com>
        msg["From"] = f"{SMTP_CONFIG['from_name']} <{SMTP_CONFIG['username']}>"
        # Para:  correo de recepción
        msg["To"] = SMTP_CONFIG['receiver_email']
        # Asunto
        msg["Subject"] = f"Formulario de contacto: {email_data.subject}"
        # Dirección para responder (correo del cliente)
        msg["Reply-To"] = email_data.client_email
        
        # Formato del mensaje
        email_content = f"""
        Nuevo mensaje de contacto:
        
        De: {email_data.client_email}
        Asunto: {email_data.subject}
        
        Mensaje:
        {email_data.message}
        """
        msg.set_content(email_content)

        # Envío del correo
        await aiosmtplib.send(
            msg,  # Mensaje como primer argumento POSICIONAL
            hostname=SMTP_CONFIG["server"],
            port=SMTP_CONFIG["port"],
            username=SMTP_CONFIG["username"],
            password=SMTP_CONFIG["password"],
            use_tls=True
        )

        return {
            "status": "success",
            "message": "Mensaje enviado correctamente",
            "client_email": email_data.client_email
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al enviar el mensaje: {str(e)}"
        )

