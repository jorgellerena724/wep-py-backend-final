from typing import Optional, List, Dict, Any
from sqlmodel import Field, SQLModel
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Column

# Modelo para las redes sociales
class SocialNetwork(BaseModel):
    network: str  # whatsapp, facebook, instagram, tiktok, x, telegram
    url: str
    username: str
    active: bool = True

# Modelo principal
class WepContactModel(SQLModel, table=True):
    __tablename__ = "contact"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(max_length=100, nullable=False)
    address: str = Field(max_length=255, nullable=True)
    social_networks: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        sa_column=Column(JSONB)
    )
    
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepContactModel(email={self.email})>"