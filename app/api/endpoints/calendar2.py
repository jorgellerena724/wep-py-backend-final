from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import datetime as dt
from googleapiclient.errors import HttpError
from ...services import GoogleCalendarManager  

router = APIRouter()

# Instancia del manager (podría ser también una dependencia)
calendar_manager = GoogleCalendarManager()

# Modelos Pydantic
class EventCreate(BaseModel):
    summary: str
    start_time: str  # Formato ISO: '2023-12-31T14:00:00'
    end_time: str    # Formato ISO: '2023-12-31T15:00:00'
    timezone: str = 'America/Havana'  # Zona horaria por defecto
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

@router.get("/events", response_model=List[EventResponse])
async def list_upcoming_events(max_results: int = 10):
    """
    Obtiene los próximos eventos del calendario.
    
    Args:
        max_results: Número máximo de eventos a devolver (por defecto 10)
    """
    try:
        events = calendar_manager.list_upcoming_events(max_results)
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener eventos: {str(e)}")

@router.post("/events", response_model=EventResponse)
async def create_event(event_data: EventCreate):
    """
    Crea un nuevo evento en Google Calendar.
    
    Requiere:
    - summary: Título del evento
    - start_time: Fecha/hora de inicio en formato ISO
    - end_time: Fecha/hora de fin en formato ISO
    """
    try:
        # Crear el evento usando el manager
        event = {
            'summary': event_data.summary,
            'description': event_data.description,
            'start': {
                'dateTime': event_data.start_time,
                'timeZone': event_data.timezone,
            },
            'end': {
                'dateTime': event_data.end_time,
                'timeZone': event_data.timezone,
            }
        }
        
        if event_data.attendees:
            event["attendees"] = [{"email": email} for email in event_data.attendees]
        
        created_event = calendar_manager.service.events().insert(
            calendarId="primary", 
            body=event
        ).execute()
        
        return EventResponse(
            id=created_event['id'],
            summary=created_event['summary'],
            start=created_event['start']['dateTime'],
            end=created_event['end']['dateTime'],
            htmlLink=created_event.get('htmlLink'),
            status=created_event.get('status')
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al crear evento: {str(e)}")

@router.put("/events/{event_id}", response_model=EventResponse)
async def update_event(event_id: str, event_data: EventUpdate):
    """
    Actualiza un evento existente en Google Calendar.
    
    Args:
        event_id: ID del evento a actualizar
    """
    try:
        # Obtener el evento actual
        event = calendar_manager.service.events().get(
            calendarId='primary', 
            eventId=event_id
        ).execute()
        
        # Actualizar campos proporcionados
        if event_data.summary:
            event['summary'] = event_data.summary
        if event_data.description:
            event['description'] = event_data.description
        if event_data.start_time:
            event['start']['dateTime'] = event_data.start_time
        if event_data.end_time:
            event['end']['dateTime'] = event_data.end_time
        
        # Actualizar el evento
        updated_event = calendar_manager.service.events().update(
            calendarId='primary',
            eventId=event_id,
            body=event
        ).execute()
        
        return EventResponse(
            id=updated_event['id'],
            summary=updated_event['summary'],
            start=updated_event['start']['dateTime'],
            end=updated_event['end']['dateTime'],
            htmlLink=updated_event.get('htmlLink'),
            status=updated_event.get('status')
        )
    except HttpError as e:
        if e.resp.status == 404:
            raise HTTPException(status_code=404, detail="Evento no encontrado")
        raise HTTPException(status_code=500, detail=f"Error al actualizar evento: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado: {str(e)}")

@router.delete("/events/{event_id}")
async def delete_event(event_id: str):
    """
    Elimina un evento de Google Calendar.
    
    Args:
        event_id: ID del evento a eliminar
    """
    try:
        calendar_manager.service.events().delete(
            calendarId='primary',
            eventId=event_id
        ).execute()
        return {"message": "Evento eliminado exitosamente"}
    except HttpError as e:
        if e.resp.status == 404:
            raise HTTPException(status_code=404, detail="Evento no encontrado")
        raise HTTPException(status_code=500, detail=f"Error al eliminar evento: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado: {str(e)}")