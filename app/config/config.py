from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field, PostgresDsn, field_validator
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv(override=True)

if os.path.exists(".env"):
    load_dotenv(dotenv_path=".env", encoding="latin-1")

class Settings(BaseSettings):
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    DEBUG: bool = Field(False, env="DEBUG")
    ALLOWED_HOSTS: str = Field("", env="ALLOWED_HOSTS")
    CORS_ALLOWED_ORIGINS: str = Field("", env="CORS_ALLOWED_ORIGINS")
    WEP_DATABASE_URL: str = Field(..., env="WEB_DATABASE_URL")
    SERVER_PORT: int = Field(3000, env="SERVER_PORT")
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")
    UPLOADS: str = Field(default="uploads", env="UPLOADS")
    MINIO_ENDPOINT: str = Field(..., env="MINIO_ENDPOINT")
    MINIO_ACCESS_KEY: str = Field(..., env="MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY: str = Field(..., env="MINIO_SECRET_KEY")
    MINIO_SECURE: str = Field(default=True, env="MINIO_SECURE")
    MINIO_BUCKET_NAME: str = Field(..., env="MINIO_BUCKET_NAME")

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