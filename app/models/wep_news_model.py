from typing import Optional
from sqlmodel import Field, SQLModel
from datetime import date
from sqlalchemy import Text

class WepNewsModel(SQLModel, table=True):
    __tablename__ = "news"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str        = Field(max_length=100, nullable=False)
    description : str = Field(sa_type=Text(), nullable=False)
    fecha: Optional[date] = Field(default=None, nullable=True) 
    photo: str        = Field(max_length=80, nullable=False)
    status: bool      = Field(nullable=False, default=True)
    order: Optional[int] = Field(default=0, nullable=True)
    
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepNewsModel(nombre={self.title})>"