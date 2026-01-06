from sqlmodel import Column, Relationship, SQLModel, Field, Text, UniqueConstraint
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional
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
    daily_token_limit: int = Field(default=100000, nullable=False)
    
    # Relación inversa
    configs: List["ChatbotConfig"] = Relationship(back_populates="model")
    usages: List["ChatbotUsage"] = Relationship(back_populates="model")

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
    
class ChatbotUsage(SQLModel, table=True):
    """
    Registra el consumo diario POR API_KEY y POR MODELO.
    Esto refleja el límite REAL de Groq.
    """
    __tablename__ = "chatbot_usage"
    __table_args__ = (
        # ✅ CAMBIO: El constraint debe ser por API_KEY + MODELO + FECHA
        UniqueConstraint("api_key", "model_id", "date", 
                        name="unique_usage_per_apikey_model_day"),
        {"schema": "public"}
    )
    
    id: Optional[int] = Field(
        default=None, 
        primary_key=True,
        sa_column_kwargs={"autoincrement": True}
    )
    
    user_id: int = Field(foreign_key="public.user2.id", index=True)
    
    api_key: str = Field(index=True, nullable=False)
    
    model_id: int = Field(foreign_key="public.chatbot_model.id", nullable=False)
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).date())
    tokens_used: int = Field(default=0)
    
    model: ChatbotModel = Relationship(back_populates="usages")