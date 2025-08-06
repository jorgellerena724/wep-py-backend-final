from typing import Optional
from sqlmodel import Field, SQLModel

class WepUserModel(SQLModel, table=True):
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