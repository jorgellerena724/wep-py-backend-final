from sqlmodel import SQLModel
from app.config.config import settings

class BaseTable(SQLModel):
    """Clase base para todos los modelos que necesitan manejar esquemas"""
    
    @classmethod
    def set_schema(cls, schema_name: str):
        """Configura el esquema dinámicamente según la base de datos"""
        if not settings.USE_SQLITE and schema_name != 'public':
            cls.__table_args__ = {"schema": schema_name}
        else:
            # Para SQLite o esquema public, no usar esquemas
            cls.__table_args__ = None
        return cls