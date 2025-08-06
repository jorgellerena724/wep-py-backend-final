from typing import Optional
from sqlmodel import Field, SQLModel

class WepContactModel(SQLModel, table=True):
    __tablename__ = "contact"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str        = Field(max_length=100, nullable=False)
    phone : str       = Field(max_length=100, nullable=False)
    address: str      = Field(max_length=255, nullable=True)
      
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepContactModel(nombre={self.email})>"