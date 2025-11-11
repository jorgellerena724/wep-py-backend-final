from typing import Optional
from sqlmodel import Field, SQLModel

class WepHeaderModel(SQLModel, table=True):
    __tablename__ = "header"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: Optional[str] = Field(max_length=100, nullable=True)
    logo: str = Field(max_length=80, nullable=True)
     
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepHeaderModel(nombre={self.name})>"
    
    @classmethod
    def set_schema(cls, schema_name: str):
        """Método para configurar el esquema dinámicamente"""
        cls.__table__.schema = schema_name if schema_name != 'public' else None
        return cls