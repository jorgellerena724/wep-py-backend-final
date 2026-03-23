from datetime import date
from typing import Dict
from sqlalchemy import Column
from sqlmodel import JSON, Field, SQLModel

class DailyMetrics(SQLModel, table=True):
    __tablename__ = "daily_metrics"

    daily_date: date = Field(default_factory=date.today, primary_key=True)
    counters: Dict[str, int] = Field(
        default_factory=dict,
        sa_column=Column(JSON)
    )

    class Config:
        arbitrary_types_allowed = True