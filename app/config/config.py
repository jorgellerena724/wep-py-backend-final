from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field, PostgresDsn, field_validator
from dotenv import load_dotenv
import os
from pathlib import Path
import json
import logging

# Configurar logging
logger = logging.getLogger(__name__)

load_dotenv(override=True)

if os.path.exists(".env"):
    load_dotenv(dotenv_path=".env", encoding="latin-1")

def parse_cors_origins(env_value: str) -> List[str]:
    """Parse CORS origins from environment variable"""
    if not env_value:
        logger.warning("⚠️ CORS_ALLOWED_ORIGINS no está configurado, usando valores por defecto")
        return ["http://localhost:3000", "http://localhost:3002", "http://localhost:4200", "http://localhost:4004"]
    
    env_value = env_value.strip()
    
    # Intentar parsear como JSON primero
    if env_value.startswith('[') and env_value.endswith(']'):
        try:
            origins = json.loads(env_value)
            logger.info(f"✅ CORS origins cargados desde JSON: {origins}")
            return origins
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ Error parseando JSON de CORS: {e}")
    
    # Fallback: parsear como string separado por comas
    origins = [origin.strip() for origin in env_value.split(",") if origin.strip()]
    logger.info(f"✅ CORS origins cargados desde string: {origins}")
    return origins

class Settings(BaseSettings):
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    DEBUG: bool = Field(False, env="DEBUG")
    ALLOWED_HOSTS: str = Field("", env="ALLOWED_HOSTS")
    CORS_ALLOWED_ORIGINS: List[str] = Field(default_factory=lambda: parse_cors_origins(os.getenv("CORS_ALLOWED_ORIGINS", "")))
    WEP_DATABASE_URL: str = Field(..., env="WEB_DATABASE_URL")
    SERVER_PORT: int = Field(3000, env="SERVER_PORT")
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")
    UPLOADS: str = Field(default="uploads", env="UPLOADS")
    MINIO_ENDPOINT: str = Field(..., env="MINIO_ENDPOINT")
    MINIO_ACCESS_KEY: str = Field(..., env="MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY: str = Field(..., env="MINIO_SECRET_KEY")
    MINIO_SECURE: str = Field(default=True, env="MINIO_SECURE")
    MINIO_BUCKET_NAME: str = Field(..., env="MINIO_BUCKET_NAME")
    USE_MINIO: bool = Field(True, env="USE_MINIO")

    @field_validator('UPLOADS')
    @classmethod
    def validate_uploads_path(cls, v: str) -> str:
       
        uploads_path = Path(v)
        if not uploads_path.is_absolute():
            uploads_path = Path.cwd() / uploads_path
        
        uploads_path.mkdir(parents=True, exist_ok=True)
        
        return str(uploads_path)

    class Config:
        env_file = ".env"
        env_file_encoding = "latin-1"
        case_sensitive = True
        extra = "allow"

settings = Settings()