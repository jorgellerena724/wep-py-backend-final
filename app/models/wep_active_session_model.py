from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel

class ActiveSessionModel(SQLModel, table=True):
    __tablename__ = "active_sessions"
    __table_args__ = {"schema": "public"}

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="public.user2.id", nullable=False)
    token: str = Field(unique=True, nullable=False)
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow, nullable=False)
    expires_at: datetime = Field(nullable=False)
    last_action: Optional[datetime] = Field(default_factory=datetime.utcnow, nullable=False)

    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<ActiveSession(user_id={self.user_id}, token={self.token[:20]}...)>"