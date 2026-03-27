from typing import Optional, List, Dict, Any
from sqlalchemy.orm.attributes import flag_modified
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import SQLModel, Session, select
from app.api.endpoints.token import verify_token
from app.config.database import get_db
from app.models.wep_metrics_config_model import MetricsConfig
from app.models.wep_user_model import WepUserModel

class CreateConfigBody(SQLModel):
    user_id: int
    events:  List[Dict[str, Any]] = []

class UpdateEventsBody(SQLModel):
    events: List[Dict[str, Any]]  # el front manda el array completo
    user_id: Optional[int] = None

router = APIRouter()

def get_config_record(db: Session, user_id: int) -> MetricsConfig:
    record = db.exec(select(MetricsConfig).where(MetricsConfig.user_id == user_id)).first()
    if not record:
        record = MetricsConfig(user_id=user_id, events=[])
        db.add(record)
        db.commit()
        db.refresh(record)
    if record.events is None:
        record.events = []
    return record

def get_active_events(db: Session, user_id: int) -> list[str]:
    record = get_config_record(db, user_id)
    return [e['event_name'] for e in record.events if isinstance(e, dict)]

# ── Listar todas las configs ──────────────────────────────────
@router.get("/")
def get_all_configs(
    db: Session = Depends(get_db),
    current_user = Depends(verify_token)
):
    configs = db.exec(select(MetricsConfig)).all()
    return [
        {
            "id":     config.id,
            "events": config.events,
            "user": {
                "id":     user.id,
                "client": user.client,
            } if (user := db.get(WepUserModel, config.user_id)) else None
        }
        for config in configs
    ]

# ── Config del usuario actual ─────────────────────────────────
@router.get("/user/")
def get_my_config(
    db: Session = Depends(get_db),
    current_user = Depends(verify_token)
):
    return get_config_record(db, current_user.id)

# ── Usuarios sin configuración ────────────────────────────────
@router.get("/users/")
def get_users_without_config(
    db: Session = Depends(get_db),
    current_user = Depends(verify_token)
):
    configured_ids = set(db.exec(select(MetricsConfig.user_id)).all())
    users = db.exec(select(WepUserModel)).all()
    return [u for u in users if u.id not in configured_ids]

# ── Crear config para un usuario ──────────────────────────────
@router.post("/", status_code=201)
def create_config(
    body: CreateConfigBody,
    db: Session = Depends(get_db),
    current_user = Depends(verify_token)
):
    existing = db.exec(select(MetricsConfig).where(MetricsConfig.user_id == body.user_id)).first()
    if existing:
        raise HTTPException(status_code=400, detail="El usuario ya tiene una configuración")

    record = MetricsConfig(user_id=body.user_id, events=body.events)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record

# ── Sobreescribir eventos completos ───────────────────────────
@router.patch("/{config_id}/")
def update_events(
    config_id: int,
    body: UpdateEventsBody,
    db: Session = Depends(get_db),
    current_user = Depends(verify_token)
):
    record = db.get(MetricsConfig, config_id)
    if not record:
        raise HTTPException(status_code=404, detail="Configuración no encontrada")

    record.events = body.events
    flag_modified(record, "events")
    db.commit()
    db.refresh(record)
    return record

# ── Eliminar config completa ──────────────────────────────────
@router.delete("/{config_id}/", status_code=204)
def delete_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(verify_token)
):
    record = db.get(MetricsConfig, config_id)
    if not record:
        raise HTTPException(status_code=404, detail="Configuración no encontrada")
    db.delete(record)
    db.commit()