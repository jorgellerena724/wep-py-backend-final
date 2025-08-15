from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import os
from googleapiclient.errors import HttpError

from app.api.endpoints.token import verify_token
from app.models.wep_user_model import WepUserModel
from app.services.google_calendar import GoogleCalendarManager

router = APIRouter()

# Modelos Pydantic
class EventCreate(BaseModel):
    summary: str
    start_time: str  # Formato ISO: '2023-12-31T14:00:00'
    end_time: str    # Formato ISO: '2023-12-31T15:00:00'
    timezone: str = 'America/Havana'
    attendees: Optional[List[str]] = None
    description: Optional[str] = None

class EventUpdate(BaseModel):
    summary: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    description: Optional[str] = None

class EventResponse(BaseModel):
    id: str
    summary: str
    start: str
    end: str
    htmlLink: Optional[str] = None
    status: Optional[str] = None

# Dependencia para obtener el calendar manager
async def get_calendar_manager(current_user: WepUserModel = Depends(verify_token)):
    client_file = f"client_secrets/{current_user.client}.json"
    
    if not os.path.exists(client_file):
        raise HTTPException(
            status_code=400,
            detail="Configuración de Google Calendar no encontrada para este usuario"
        )
    
    return GoogleCalendarManager(
        user_id=str(current_user.id),
        client_secret_file=client_file
    )

@router.get("/events", response_model=List[EventResponse])
async def list_upcoming_events(
    max_results: int = 10,
    manager: GoogleCalendarManager = Depends(get_calendar_manager),
    current_user: WepUserModel = Depends(verify_token)
):
    try:
        events = manager.list_upcoming_events(max_results)
        return [
            EventResponse(
                id=event['id'],
                summary=event['summary'],
                start=event['start'].get('dateTime', event['start'].get('date')),
                end=event['end'].get('dateTime', event['end'].get('date')),
                htmlLink=event.get('htmlLink'),
                status=event.get('status')
            )
            for event in events
        ]
    except HttpError as e:
        if e.resp.status == 403:
            raise HTTPException(status_code=403, detail="No tiene permisos para acceder al calendario")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener eventos: {str(e)}")

@router.post("/events", response_model=EventResponse)
async def create_event(
    event_data: EventCreate,
    manager: GoogleCalendarManager = Depends(get_calendar_manager),
    current_user: WepUserModel = Depends(verify_token)
):
    try:
        created_event = manager.create_event(
            summary=event_data.summary,
            start_time=event_data.start_time,
            end_time=event_data.end_time,
            timezone=event_data.timezone,
            attendees=event_data.attendees,
            description=event_data.description
        )
        
        return EventResponse(
            id=created_event['id'],
            summary=created_event['summary'],
            start=created_event['start']['dateTime'],
            end=created_event['end']['dateTime'],
            htmlLink=created_event.get('htmlLink'),
            status=created_event.get('status')
        )
    except HttpError as e:
        if e.resp.status == 403:
            raise HTTPException(status_code=403, detail="No tiene permisos para crear eventos")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al crear evento: {str(e)}")

@router.put("/events/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: str,
    event_data: EventUpdate,
    manager: GoogleCalendarManager = Depends(get_calendar_manager),
    current_user: WepUserModel = Depends(verify_token)
):
    try:
        updated_event = manager.update_event(
            event_id=event_id,
            summary=event_data.summary,
            start_time=event_data.start_time,
            end_time=event_data.end_time,
            description=event_data.description
        )
        
        return EventResponse(
            id=updated_event['id'],
            summary=updated_event['summary'],
            start=updated_event['start']['dateTime'],
            end=updated_event['end']['dateTime'],
            htmlLink=updated_event.get('htmlLink'),
            status=updated_event.get('status')
        )
    except HttpError as e:
        if e.resp.status == 403:
            raise HTTPException(status_code=403, detail="No tiene permisos para actualizar eventos")
        elif e.resp.status == 404:
            raise HTTPException(status_code=404, detail="Evento no encontrado")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar evento: {str(e)}")

@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    manager: GoogleCalendarManager = Depends(get_calendar_manager),
    current_user: WepUserModel = Depends(verify_token)
):
    try:
        manager.delete_event(event_id)
        return {"message": "Evento eliminado exitosamente"}
    except HttpError as e:
        if e.resp.status == 403:
            raise HTTPException(status_code=403, detail="No tiene permisos para eliminar eventos")
        elif e.resp.status == 404:
            raise HTTPException(status_code=404, detail="Evento no encontrado")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar evento: {str(e)}")