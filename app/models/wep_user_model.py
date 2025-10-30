from typing import Optional
from sqlmodel import Field, SQLModel
from app.config.config import settings

class WepUserModel(SQLModel, table=True):
    if settings.USE_SQLITE:
        __tablename__ = "user2"
    else:
        __tablename__ = "user2"
        __table_args__ = {"schema": "public"}

    id: Optional[int] = Field(default=None, primary_key=True)
    password: str = Field(max_length=255, nullable=False)
    full_name: str = Field(max_length=96, nullable=False)
    email: str = Field(max_length=96, nullable=False)
    client: str = Field(max_length=50, nullable=True)
   
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepUserModel(nombre={self.email})>"