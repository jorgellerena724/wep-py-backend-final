from typing import Optional
from sqlmodel import Field, SQLModel
from datetime import datetime

class GoogleCalendarToken(SQLModel, table=True):
    __tablename__ = "google_calendar_tokens"
    __table_args__ = {"schema": "public"}

    id: Optional[int] = Field(default=None, primary_key=True)
    client: str = Field(max_length=50, nullable=False)  # tenant
    access_token: str = Field(nullable=False)
    refresh_token: str = Field(nullable=False)
    token_expiry: datetime = Field(nullable=False)
    token_uri: str = Field(nullable=False)
    client_id: str = Field(nullable=False)
    client_secret: str = Field(nullable=False)
    scopes: str = Field(nullable=False)
