import os
from typing import Optional
from pydantic_settings import BaseSettings

class ChatbotSettings(BaseSettings):
    """
    Configuración específica para el chatbot.
    Todas las variables pueden sobrescribirse con variables de entorno.
    """
    
    # API Key de Groq (REQUERIDA)
    GROQ_API_KEY: str
    
    # Configuración por defecto para nuevos clientes
    DEFAULT_GROQ_MODEL: str = "llama-3.3-70b-versatile"
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_MAX_TOKENS: int = 500
    DEFAULT_SESSION_TTL_MINUTES: int = 30
    DEFAULT_MAX_HISTORY: int = 10
    
    # Límites de seguridad
    MAX_MESSAGE_LENGTH: int = 2000
    MAX_SESSIONS_PER_USER: int = 5
    MAX_TOKENS_PER_REQUEST: int = 2000
    
    # Intervalos de mantenimiento
    CLEANUP_INTERVAL_MINUTES: int = 60  # Limpiar sesiones cada hora
    STATS_UPDATE_INTERVAL_MINUTES: int = 5
    
    # Características habilitadas/deshabilitadas
    ENABLE_STREAMING: bool = False
    ENABLE_SUGGESTIONS: bool = True
    ENABLE_ANALYTICS: bool = True
    ENABLE_HISTORY: bool = True
    
    # Configuración de respuesta de error
    SHOW_DETAILED_ERRORS: bool = False  # Mostrar detalles técnicos de errores
    FALLBACK_RESPONSE: str = "Lo siento, estoy teniendo dificultades técnicas en este momento. Por favor, intenta de nuevo más tarde."
    
    # Configuración de logs
    LOG_LEVEL: str = "INFO"
    LOG_REQUESTS: bool = True
    
    # Tiempos de espera
    GROQ_TIMEOUT_SECONDS: int = 30
    DB_TIMEOUT_SECONDS: int = 10
    
    # Configuración de cache (opcional)
    ENABLE_CACHE: bool = False
    CACHE_TTL_SECONDS: int = 300
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

# Instancia global de configuración
chatbot_settings = ChatbotSettings()


def validate_configuration():
    """
    Valida que la configuración requerida esté presente.
    """
    missing_vars = []
    
    if not chatbot_settings.GROQ_API_KEY:
        missing_vars.append("GROQ_API_KEY")
    
    if missing_vars:
        raise ValueError(
            f"Variables de entorno requeridas faltantes: {', '.join(missing_vars)}. "
            f"Por favor, configura estas variables en el archivo .env"
        )
    
    # Validar rangos
    if not 0.0 <= chatbot_settings.DEFAULT_TEMPERATURE <= 2.0:
        raise ValueError("DEFAULT_TEMPERATURE debe estar entre 0.0 y 2.0")
    
    if chatbot_settings.DEFAULT_MAX_TOKENS <= 0:
        raise ValueError("DEFAULT_MAX_TOKENS debe ser mayor a 0")
    
    if chatbot_settings.DEFAULT_SESSION_TTL_MINUTES <= 0:
        raise ValueError("DEFAULT_SESSION_TTL_MINUTES debe ser mayor a 0")
    
    return True


# Validar al importar
try:
    validate_configuration()
    print("✅ Configuración del chatbot validada correctamente")
except ValueError as e:
    print(f"❌ Error en configuración: {e}")
    raise