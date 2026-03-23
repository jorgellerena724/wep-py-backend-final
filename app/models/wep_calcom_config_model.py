from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class CalComConfig(SQLModel, table=True):
    __tablename__ = "calcom_config"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Credenciales Cal.com
    api_key: str = Field(max_length=255)           # Encriptar en reposo (ej: con pgcrypto o a nivel app)
    webhook_secret: Optional[str] = Field(default=None, max_length=255)  # Para validar payloads entrantes

    # Identidad del tenant en Cal.com
    cal_user_id: Optional[int] = Field(default=None)        # ID numérico del user en Cal.com
    cal_username: Optional[str] = Field(default=None, max_length=100)    # Para construir links: cal.com/{username}
    
    # Configuración operativa
    default_event_type_id: Optional[int] = Field(default=None)  # El event type que usa este tenant
    time_zone: str = Field(default="America/Bogota", max_length=60)

    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))

    class Config:
        arbitrary_types_allowed = True