from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, ConfigDict
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv(override=True)

if os.path.exists(".env"):
    load_dotenv(dotenv_path=".env", encoding="latin-1")

class Settings(BaseSettings):
    """
    Configuración unificada de toda la aplicación.
    """
    
    # ============================================
    # CONFIGURACIÓN PRINCIPAL DE LA APLICACIÓN
    # ============================================
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    DEBUG: bool = Field(False, env="DEBUG")
    ALLOWED_HOSTS: str = Field("", env="ALLOWED_HOSTS")
    CORS_ALLOWED_ORIGINS: str = Field("", env="CORS_ALLOWED_ORIGINS")
    WEP_DATABASE_URL: str = Field(..., env="WEB_DATABASE_URL")
    SERVER_PORT: int = Field(3000, env="SERVER_PORT")
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")
    UPLOADS: str = Field(default="uploads", env="UPLOADS")
    USE_SQLITE: bool = Field(False, env="USE_SQLITE")
    SQLITE_DB_PATH: str = Field("wep_database.db", env="SQLITE_DB_PATH")
    
    # ============================================
    # CONFIGURACIÓN DE EMAIL (SMTP)
    # ============================================
    SMTP_SERVER: Optional[str] = Field(None, env="SMTP_SERVER")
    SMTP_PORT: Optional[int] = Field(None, env="SMTP_PORT")
    SMTP_USERNAME: Optional[str] = Field(None, env="SMTP_USERNAME")
    SMTP_PASSWORD: Optional[str] = Field(None, env="SMTP_PASSWORD")
    RECEIVER_EMAIL: Optional[str] = Field(None, env="RECEIVER_EMAIL")
    FROM_NAME: Optional[str] = Field(None, env="FROM_NAME")
    
    
    # ============================================
    # VALIDACIONES
    # ============================================
    
    @field_validator('UPLOADS')
    @classmethod
    def validate_uploads_path(cls, v: str) -> str:
        uploads_path = Path(v)
        if not uploads_path.is_absolute():
            uploads_path = Path.cwd() / uploads_path
        
        uploads_path.mkdir(parents=True, exist_ok=True)
        return str(uploads_path)

    @field_validator('SQLITE_DB_PATH')
    @classmethod
    def validate_sqlite_path(cls, v: str) -> str:
        sqlite_path = Path(v)
        if not sqlite_path.is_absolute():
            sqlite_path = Path.cwd() / sqlite_path
        
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return str(sqlite_path)
    
    def get_database_url(self) -> str:
        """Retorna la URL de base de datos según la configuración"""
        if self.USE_SQLITE:
            return f"sqlite:///{self.SQLITE_DB_PATH}"
        else:
            # Aseguramos que use 'postgresql://' en lugar de 'postgres://'
            return self.WEP_DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    # Configuración de Pydantic
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="latin-1",
        case_sensitive=False,
        extra='ignore'  # Ignorar variables extra no definidas
    )


# Instancia global de configuración
settings = Settings()