from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlmodel import Session
from datetime import datetime
import json

from app.models.wep_google_calendar_token import GoogleCalendarToken
from .token import get_current_tenant
from app.config.database import get_db

router = APIRouter()

CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

@router.get("/auth")
def google_calendar_auth(
    tenant: str = Depends(get_current_tenant)
):
    # Guardar tenant en state para recuperarlo en callback
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri="http://localhost:8000/google-calendar/callback"
    )
    auth_url, state = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true",
        state=tenant
    )
    return RedirectResponse(auth_url)

@router.get("/callback")
def google_calendar_callback(
    request: Request,
    db: Session = Depends(get_db)
):
    state = request.query_params.get("state")
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri="http://localhost:8000/calendar/callback",
        state=state
    )
    flow.fetch_token(authorization_response=str(request.url))
    creds = flow.credentials

    # Guardar credenciales en DB
    db_token = GoogleCalendarToken(
        client=state,
        access_token=creds.token,
        refresh_token=creds.refresh_token,
        token_expiry=creds.expiry,
        token_uri=creds.token_uri,
        client_id=creds.client_id,
        client_secret=creds.client_secret,
        scopes=json.dumps(creds.scopes)
    )
    db.add(db_token)
    db.commit()
    return {"status": f"Google Calendar conectado para {state}"}

@router.post("/create-event")
def create_event(
    resumen: str,
    descripcion: str,
    inicio: str,
    fin: str,
    tenant: str = Depends(get_current_tenant),  # Usa FRONT TOKEN para obtener tenant
    db: Session = Depends(get_db)
):
    # Buscar tokens en la base de datos para ese tenant
    token = db.query(GoogleCalendarToken).filter(GoogleCalendarToken.client == tenant).first()
    if not token:
        return {"error": f"Tenant '{tenant}' no conectado a Google Calendar"}

    creds = Credentials(
        token.access_token,
        refresh_token=token.refresh_token,
        token_uri=token.token_uri,
        client_id=token.client_id,
        client_secret=token.client_secret,
        scopes=json.loads(token.scopes)
    )

    service = build("calendar", "v3", credentials=creds)
    event = {
        "summary": resumen,
        "description": descripcion,
        "start": {"dateTime": inicio, "timeZone": "America/New_York"},
        "end": {"dateTime": fin, "timeZone": "America/New_York"},
    }
    service.events().insert(calendarId="primary", body=event).execute()
    return {"status": "Evento creado", "tenant": tenant}