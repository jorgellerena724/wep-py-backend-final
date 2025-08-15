import os.path
import datetime as dt
from typing import Optional
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar"]

class GoogleCalendarManager:
    def __init__(self, user_id: str, client_secret_file: str):
        """
        Inicializa el manager para un usuario específico.
        
        Args:
            user_id: ID del usuario para manejar tokens únicos
            client_secret_file: Ruta al archivo client_secret del usuario
        """
        self.user_id = user_id
        self.client_secret_file = client_secret_file
        self.token_file = f"tokens/{user_id}_token.json"
        self.service = self._authenticate()

    def _authenticate(self):
        """Autentica al usuario y devuelve el servicio de Google Calendar."""
        creds = None
        Path("tokens").mkdir(exist_ok=True)  # Asegura que exista el directorio

        # Cargar token existente si existe
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)

        # Si no hay credenciales válidas, autenticar
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.client_secret_file):
                    raise FileNotFoundError(
                        f"Archivo de credenciales no encontrado: {self.client_secret_file}"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secret_file, 
                    SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Guardar credenciales para el próximo uso
            with open(self.token_file, "w") as token:
                token.write(creds.to_json())

        return build("calendar", "v3", credentials=creds)

    def list_upcoming_events(self, max_results=10):
        """Lista eventos próximos del calendario."""
        try:
            now = dt.datetime.utcnow().isoformat() + "Z"
            tomorrow = (dt.datetime.now() + dt.timedelta(days=5)).replace(
                hour=23, minute=59, second=0, microsecond=0
            ).isoformat() + "Z"

            events_result = self.service.events().list(
                calendarId='primary', 
                timeMin=now, 
                timeMax=tomorrow,
                maxResults=max_results, 
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            return events_result.get('items', [])
        except HttpError as error:
            error_msg = f"Error al listar eventos: {error}"
            if error.resp.status == 403:
                error_msg += " - Permisos insuficientes"
            raise Exception(error_msg)

    def create_event(self, summary, start_time, end_time, timezone, attendees=None, description=None):
        """Crea un nuevo evento en el calendario."""
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': timezone,
            },
            'end': {
                'dateTime': end_time,
                'timeZone': timezone,
            }
        }

        if attendees:
            event["attendees"] = [{"email": email} for email in attendees]

        try:
            return self.service.events().insert(
                calendarId="primary", 
                body=event
            ).execute()
        except HttpError as error:
            error_msg = f"Error al crear evento: {error}"
            if error.resp.status == 403:
                error_msg += " - Permisos insuficientes"
            elif error.resp.status == 400:
                error_msg += " - Datos del evento inválidos"
            raise Exception(error_msg)

    def update_event(self, event_id, summary=None, start_time=None, end_time=None, description=None):
        """Actualiza un evento existente."""
        try:
            event = self.service.events().get(
                calendarId='primary', 
                eventId=event_id
            ).execute()

            if summary:
                event['summary'] = summary
            if description:
                event['description'] = description
            if start_time:
                event['start']['dateTime'] = start_time
            if end_time:
                event['end']['dateTime'] = end_time

            return self.service.events().update(
                calendarId='primary', 
                eventId=event_id, 
                body=event
            ).execute()
        except HttpError as error:
            error_msg = f"Error al actualizar evento: {error}"
            if error.resp.status == 403:
                error_msg += " - Permisos insuficientes"
            elif error.resp.status == 404:
                error_msg = "Evento no encontrado"
            raise Exception(error_msg)

    def delete_event(self, event_id):
        """Elimina un evento del calendario."""
        try:
            self.service.events().delete(
                calendarId='primary',
                eventId=event_id
            ).execute()
            return True
        except HttpError as error:
            error_msg = f"Error al eliminar evento: {error}"
            if error.resp.status == 403:
                error_msg += " - Permisos insuficientes"
            elif error.resp.status == 404:
                error_msg = "Evento no encontrado"
            raise Exception(error_msg)