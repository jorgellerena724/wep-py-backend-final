from typing import Optional
from sqlalchemy.orm.attributes import flag_modified
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.api.endpoints.token import get_tenant_session, verify_token
from app.models.wep_metrics_config_model import MetricEvent, MetricsConfig

router = APIRouter()


def get_config_record(db: Session, user_id: int) -> MetricsConfig:
    record = db.exec(select(MetricsConfig).where(MetricsConfig.user_id == user_id)).first()
    if not record:
        record = MetricsConfig(user_id=user_id, events=[])
        db.add(record)
        db.commit()
        db.refresh(record)
    # Si existe pero events es None, normalizar a lista vacía
    if record.events is None:
        record.events = []
    return record

def get_active_events(db: Session, user_id: int) -> list[str]:
    record = get_config_record(db, user_id)
    if not record.events:          # ← cubre None y []
        return []
    return [
        e['event_name'] 
        for e in record.events 
        if isinstance(e, dict) and e.get('is_active', True)
    ]

@router.get("/config/")
def get_config(
    db: Session = Depends(get_tenant_session),
    current_user = Depends(verify_token)
):
    return get_config_record(db, current_user.id)

@router.post("/config/event/", status_code=201)
def add_event(
    event_name: str,
    label: str,
    db: Session = Depends(get_tenant_session),
    current_user = Depends(verify_token)
):
    record = get_config_record(db, current_user.id)

    if any(e['event_name'] == event_name for e in record.events):
        raise HTTPException(status_code=400, detail="El evento ya existe")

    new_event = MetricEvent(event_name=event_name, label=label).model_dump()
    record.events = [*record.events, new_event]
    flag_modified(record, "events")
    db.commit()
    db.merge(record)
    return record


@router.patch("/config/event/{event_name}/")
def update_event(
    event_name: str,
    label: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_tenant_session),
    current_user = Depends(verify_token)
):
    record = get_config_record(db, current_user.id)

    # ✅ Buscar el dict completo, no solo el nombre
    event_dict = next((e for e in record.events if e['event_name'] == event_name), None)
    if not event_dict:
        raise HTTPException(status_code=404, detail="Evento no encontrado")

    # ✅ Mutar el dict directamente
    if label     is not None: event_dict['label']     = label
    if is_active is not None: event_dict['is_active'] = is_active

    # Nueva referencia para que flag_modified funcione
    record.events = [*record.events]
    flag_modified(record, "events")
    db.commit()
    db.refresh(record)
    return record


@router.delete("/config/event/{event_name}/", status_code=204)
def delete_event(
    event_name: str,
    db: Session = Depends(get_tenant_session),
    current_user = Depends(verify_token)
):
    record = get_config_record(db, current_user.id)

    if not any(e['event_name'] == event_name for e in record.events):
        raise HTTPException(status_code=404, detail="Evento no encontrado")

    record.events = [e for e in record.events if e['event_name'] != event_name]
    flag_modified(record, "events")
    db.commit()