from typing import Optional
from sqlmodel import Field, SQLModel
from sqlalchemy import Text


class WepManagerModel(SQLModel, table=True):
    __tablename__ = "manager"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str        = Field(max_length=100, nullable=False)
    description : str = Field(sa_type=Text(), nullable=False)
    charge : str      = Field(max_length=100, nullable=False)
    photo: str        = Field(max_length=80, nullable=True)
      
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepManagerModel(nombre={self.title})>"
    