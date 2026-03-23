from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Column
from sqlmodel import Field, SQLModel

class MetricEvent(BaseModel):
    event_name: str
    label:      str
    is_active:  bool = True

class MetricsConfig(SQLModel, table=True):
    __tablename__ = "metrics_config"

    id:     Optional[int]                    = Field(default=None, primary_key=True)
    events: Optional[List[Dict[str, Any]]]   = Field(      # ← igual que social_networks
        default=None,
        sa_column=Column(JSONB)
    )

    class Config:
        arbitrary_types_allowed = True