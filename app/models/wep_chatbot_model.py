from sqlmodel import Column, Relationship, SQLModel, Field, Text
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, Dict, Any
from app.config.config import settings

if TYPE_CHECKING:
    from app.models.wep_user_model import WepUserModel
    
class ChatbotModel(SQLModel, table=True):
    """
    Modelos de IA disponibles para los chatbots.
    Gestiona los modelos de Groq desde la base de datos.
    """
    __tablename__ = "chatbot_model"
    __table_args__ = {"schema": "public"}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    provider: str = Field(nullable=False)
    status: bool = Field(default=True)
    
    # Relación inversa
    configs: list["ChatbotConfig"] = Relationship(back_populates="model")

class ChatbotConfig(SQLModel, table=True):
    """
    Configuración del chatbot por usuario.
    Desde el dashboard asignas qué config usar cada user_id.
    """
    if settings.USE_SQLITE:
        __tablename__ = "chatbot_config"
    else:
        __tablename__ = "chatbot_config"
        __table_args__ = {"schema": "public"}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="public.user2.id", nullable=False, unique=True)
    
    # Configuración de Groq
    api_key: str = Field()
    model_id: int = Field(
        foreign_key="public.chatbot_model.id",
    )
    prompt: str = Field(
        sa_column=Column(Text), 
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
    )
    
    status: bool = Field(default=True)
    created_at: datetime = Field()
    updated_at: datetime = Field()
    
    # Relación con usuario
    user: Optional["WepUserModel"] = Relationship(
        back_populates="chatbot",
        sa_relationship_kwargs={"lazy": "joined"}
    )
    
    model: Optional["ChatbotModel"] = Relationship(
        back_populates="configs",
        sa_relationship_kwargs={"lazy": "joined"}
    )

class ChatSession(SQLModel, table=True):
    """
    Sesión de chat para cada usuario final.
    Se crea una por cada usuario que interactúa con el chatbot.
    """
    if settings.USE_SQLITE:
        __tablename__ = "chat_sessions"
    else:
        __tablename__ = "chat_sessions"
        __table_args__ = {"schema": "public"}
    
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
    meta_data: Optional[str] = Field(default=None, description="Metadatos adicionales en JSON")


class ChatMessage(SQLModel, table=True):
    """
    Mensaje individual de una conversación.
    Se relaciona con una sesión específica.
    """
    if settings.USE_SQLITE:
        __tablename__ = "chat_messages"
    else:
        __tablename__ = "chat_messages"
        __table_args__ = {"schema": "public"}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Relación con la sesión
    session_key: str = Field(
        foreign_key="public.chat_sessions.session_key",
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
    if settings.USE_SQLITE:
        __tablename__ = "chatbot_usage_stats"
    else:
        __tablename__ = "chatbot_usage_stats"
        __table_args__ = {"schema": "public"}
    
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