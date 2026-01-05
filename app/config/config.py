from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, PostgresDsn, field_validator, ConfigDict
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
    # CONFIGURACIÓN DEL CHATBOT
    # ============================================
    GROQ_API_KEY: str = Field(..., env="GROQ_API_KEY")
    
    # Configuración por defecto para nuevos clientes
    DEFAULT_GROQ_MODEL: str = Field("llama-3.3-70b-versatile", env="DEFAULT_GROQ_MODEL")
    DEFAULT_TEMPERATURE: float = Field(0.7, env="DEFAULT_TEMPERATURE")
    DEFAULT_MAX_TOKENS: int = Field(500, env="DEFAULT_MAX_TOKENS")
    DEFAULT_SESSION_TTL_MINUTES: int = Field(30, env="DEFAULT_SESSION_TTL_MINUTES")
    DEFAULT_MAX_HISTORY: int = Field(10, env="DEFAULT_MAX_HISTORY")
    
    # Límites de seguridad
    MAX_MESSAGE_LENGTH: int = Field(2000, env="MAX_MESSAGE_LENGTH")
    MAX_SESSIONS_PER_USER: int = Field(5, env="MAX_SESSIONS_PER_USER")
    MAX_TOKENS_PER_REQUEST: int = Field(2000, env="MAX_TOKENS_PER_REQUEST")
    
    # Intervalos de mantenimiento
    CLEANUP_INTERVAL_MINUTES: int = Field(60, env="CLEANUP_INTERVAL_MINUTES")
    STATS_UPDATE_INTERVAL_MINUTES: int = Field(5, env="STATS_UPDATE_INTERVAL_MINUTES")
    
    # Características habilitadas/deshabilitadas
    ENABLE_STREAMING: bool = Field(False, env="ENABLE_STREAMING")
    ENABLE_SUGGESTIONS: bool = Field(True, env="ENABLE_SUGGESTIONS")
    ENABLE_ANALYTICS: bool = Field(True, env="ENABLE_ANALYTICS")
    ENABLE_HISTORY: bool = Field(True, env="ENABLE_HISTORY")
    
    # Configuración de respuesta de error
    SHOW_DETAILED_ERRORS: bool = Field(False, env="SHOW_DETAILED_ERRORS")
    FALLBACK_RESPONSE: str = Field(
        "Lo siento, estoy teniendo dificultades técnicas en este momento. Por favor, intenta de nuevo más tarde.",
        env="FALLBACK_RESPONSE"
    )
    
    # Configuración de logs
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    LOG_REQUESTS: bool = Field(True, env="LOG_REQUESTS")
    
    # Tiempos de espera
    GROQ_TIMEOUT_SECONDS: int = Field(30, env="GROQ_TIMEOUT_SECONDS")
    DB_TIMEOUT_SECONDS: int = Field(10, env="DB_TIMEOUT_SECONDS")
    
    # Configuración de cache (opcional)
    ENABLE_CACHE: bool = Field(False, env="ENABLE_CACHE")
    CACHE_TTL_SECONDS: int = Field(300, env="CACHE_TTL_SECONDS")
    
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
    
    @field_validator('DEFAULT_TEMPERATURE')
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("DEFAULT_TEMPERATURE debe estar entre 0.0 y 2.0")
        return v
    
    @field_validator('DEFAULT_MAX_TOKENS', 'MAX_TOKENS_PER_REQUEST')
    @classmethod
    def validate_positive_integer(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("El valor debe ser mayor a 0")
        return v

    def get_database_url(self) -> str:
        """Retorna la URL de base de datos según la configuración"""
        if self.USE_SQLITE:
            return f"sqlite:///{self.SQLITE_DB_PATH}"
        else:
            # Aseguramos que use 'postgresql://' en lugar de 'postgres://'
            return self.WEP_DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    def validate_chatbot_config(self):
        """Valida la configuración específica del chatbot"""
        if not self.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY es requerida para el chatbot")
        
        if self.DEFAULT_SESSION_TTL_MINUTES <= 0:
            raise ValueError("DEFAULT_SESSION_TTL_MINUTES debe ser mayor a 0")
        
        return True
    
    # Configuración de Pydantic
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="latin-1",
        case_sensitive=False,
        extra='ignore'  # Ignorar variables extra no definidas
    )


# Instancia global de configuración
settings = Settings()

# Validar configuración del chatbot al iniciar
try:
    settings.validate_chatbot_config()
    print("✅ Configuración del chatbot validada correctamente")
except ValueError as e:
    print(f"❌ Error en configuración del chatbot: {e}")
    raise