from typing import List, Optional, Dict, Any, TYPE_CHECKING
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Column
from sqlmodel import Field, SQLModel, Relationship

if TYPE_CHECKING:
    from app.models.wep_user_model import WepUserModel

class MetricEvent(BaseModel):
    event_name: str
    label:      str
    is_active:  bool = True

class MetricsConfig(SQLModel, table=True):
    __tablename__ = "metrics_config"
    __table_args__  = {"schema": "public"}

    id:      Optional[int]                   = Field(default=None, primary_key=True)
    user_id: int                            = Field(foreign_key="public.user2.id", nullable=False, unique=True)
    events:  Optional[List[Dict[str, Any]]]  = Field(
        default=None,
        sa_column=Column(JSONB)
    )

    # Relación con usuario
    user: Optional["WepUserModel"] = Relationship(
        back_populates="metrics_config",
        sa_relationship_kwargs={"lazy": "joined"}
    )

    class Config:
        arbitrary_types_allowed = True