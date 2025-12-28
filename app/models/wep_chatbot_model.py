from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional, Dict, Any
import json

class ChatbotConfig(SQLModel, table=True):
    """
    Configuración del chatbot para cada cliente/tenant.
    Esta tabla se creará en el esquema de cada cliente.
    """
    __tablename__ = "chatbot_config"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, description="ID del cliente/tenant")
    
    # Configuración de Groq
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Modelo de Groq a usar")
    system_prompt: str = Field(
        default="Eres un asistente virtual útil y amable. Responde en español de manera profesional.",
        description="Prompt del sistema personalizado para el cliente"
    )
    
    # Parámetros de generación
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Creatividad de las respuestas (0-2)")
    max_tokens: int = Field(default=500, description="Máximo de tokens por respuesta")
    max_history: int = Field(default=10, description="Máximo de mensajes en historial")
    
    # Configuración de sesiones
    session_ttl_minutes: int = Field(default=30, description="Tiempo de expiración de sesiones en minutos")
    enable_history: bool = Field(default=True, description="Guardar historial de conversaciones")
    
    # Información del negocio
    company_name: Optional[str] = Field(default=None, description="Nombre de la empresa")
    company_description: Optional[str] = Field(default=None, description="Descripción del negocio")
    contact_info: Optional[str] = Field(default=None, description="Información de contacto (JSON)")
    
    # Configuración adicional
    branding: Optional[str] = Field(default=None, description="Configuración de marca (JSON)")
    welcome_message: Optional[str] = Field(default=None, description="Mensaje de bienvenida personalizado")
    
    # Metadatos
    is_active: bool = Field(default=True, description="Chatbot activo/inactivo")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def get_contact_info_dict(self) -> Dict[str, Any]:
        """Devuelve la información de contacto como diccionario"""
        if self.contact_info:
            try:
                return json.loads(self.contact_info)
            except:
                return {}
        return {}
    
    def get_branding_dict(self) -> Dict[str, Any]:
        """Devuelve la configuración de marca como diccionario"""
        if self.branding:
            try:
                return json.loads(self.branding)
            except:
                return {}
        return {}


class ChatSession(SQLModel, table=True):
    """
    Sesión de chat para cada usuario final.
    Se crea una por cada usuario que interactúa con el chatbot.
    """
    __tablename__ = "chat_sessions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Identificación
    session_key: str = Field(unique=True, index=True, description="Clave única de la sesión")
    tenant_id: str = Field(index=True, description="ID del cliente/tenant")
    
    # Información del usuario final
    user_identifier: Optional[str] = Field(default=None, description="Identificador del usuario (email, ID, etc.)")
    user_ip: Optional[str] = Field(default=None, description="Dirección IP del usuario")
    user_agent: Optional[str] = Field(default=None, description="User-Agent del navegador")
    page_url: Optional[str] = Field(default=None, description="URL de la página donde inició el chat")
    
    # Metadatos de la sesión
    message_count: int = Field(default=0, description="Número total de mensajes en la sesión")
    is_active: bool = Field(default=True, description="Sesión activa/inactiva")
    
    # Tiempos
    created_at: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        description="Fecha de expiración de la sesión"
    )
    
    # Datos adicionales (opcional)
    metadata: Optional[str] = Field(default=None, description="Metadatos adicionales en JSON")


class ChatMessage(SQLModel, table=True):
    """
    Mensaje individual de una conversación.
    Se relaciona con una sesión específica.
    """
    __tablename__ = "chat_messages"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Relación con la sesión
    session_key: str = Field(
        foreign_key="chat_sessions.session_key",
        index=True,
        description="Clave de la sesión a la que pertenece"
    )
    
    # Contenido del mensaje
    role: str = Field(description="Rol: 'user', 'assistant' o 'system'")
    content: str = Field(description="Contenido del mensaje")
    
    # Metadatos del mensaje
    tokens: Optional[int] = Field(default=None, description="Tokens utilizados")
    model_used: Optional[str] = Field(default=None, description="Modelo usado para generar la respuesta")
    
    # Tiempo
    created_at: datetime = Field(default_factory=datetime.now)
    
    # Orden en la conversación
    message_order: int = Field(default=0, description="Orden del mensaje en la conversación")


class ChatbotUsageStats(SQLModel, table=True):
    """
    Estadísticas de uso del chatbot por cliente.
    Opcional: para monitoreo y facturación.
    """
    __tablename__ = "chatbot_usage_stats"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Identificación
    tenant_id: str = Field(index=True, description="ID del cliente/tenant")
    date: str = Field(index=True, description="Fecha en formato YYYY-MM-DD")
    
    # Contadores
    total_sessions: int = Field(default=0, description="Total de sesiones creadas")
    active_sessions: int = Field(default=0, description="Sesiones activas")
    total_messages: int = Field(default=0, description="Total de mensajes procesados")
    total_tokens: int = Field(default=0, description="Total de tokens consumidos")
    
    # Costos estimados (opcional)
    estimated_cost: float = Field(default=0.0, description="Costo estimado en USD")
    
    # Tiempo
    updated_at: datetime = Field(default_factory=datetime.now)


# Modelos Pydantic para requests/responses
from pydantic import BaseModel
from typing import Dict, Any, Optional as Opt

class ChatRequest(BaseModel):
    """Modelo para peticiones de chat"""
    message: str
    session_key: Opt[str] = None
    user_context: Opt[Dict[str, Any]] = None
    reset_conversation: bool = False

class ChatResponse(BaseModel):
    """Modelo para respuestas del chatbot"""
    response: str
    session_key: str
    model_used: Opt[str] = None
    usage: Opt[Dict[str, int]] = None
    suggestions: Opt[list] = None
    timestamp: datetime = datetime.now()

class SessionInfo(BaseModel):
    """Información de una sesión"""
    session_key: str
    tenant_id: str
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    message_count: int
    is_active: bool

class ChatbotConfigUpdate(BaseModel):
    """Modelo para actualizar configuración"""
    groq_model: Opt[str] = None
    system_prompt: Opt[str] = None
    temperature: Opt[float] = None
    max_tokens: Opt[int] = None
    max_history: Opt[int] = None
    session_ttl_minutes: Opt[int] = None
    company_name: Opt[str] = None
    company_description: Opt[str] = None
    contact_info: Opt[Dict[str, Any]] = None
    branding: Opt[Dict[str, Any]] = None
    welcome_message: Opt[str] = None
    is_active: Opt[bool] = None