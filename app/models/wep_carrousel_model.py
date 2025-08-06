from typing import Optional
from sqlmodel import Field, SQLModel
from sqlalchemy import Text

class WepCarrouselModel(SQLModel, table=True):
    __tablename__ = "carrousel"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str        = Field(max_length=100, nullable=False)
    description : str = Field(sa_type=Text(), nullable=False)
    photo: str        = Field(max_length=80, nullable=True)
    status: bool      = Field(nullable=False, default=True)
   
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepCarrouselModel(nombre={self.title})>"