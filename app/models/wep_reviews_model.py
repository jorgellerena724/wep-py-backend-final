from typing import Optional
from sqlmodel import Field, SQLModel
from datetime import date
from sqlalchemy import Text

class WepReviewsModel(SQLModel, table=True):
    __tablename__ = "reviews"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str        = Field(max_length=100, nullable=False)
    description : str = Field(sa_type=Text(), nullable=False)
    photo: str        = Field(max_length=80, nullable=False)  
   
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepReviewsModel(nombre={self.title})>"