import logging
from datetime import datetime, timezone
from sqlalchemy.orm import selectinload
from typing import Any, Dict, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import SQLModel, Session, select
import hashlib
from app.api.endpoints.user import UserResponse
from app.models.wep_chatbot_model import (
    ChatbotConfig,
    ChatbotModel,
    ChatbotUsage,
)
from app.models.wep_user_model import WepUserModel
from app.services.chatbot import get_chatbot_service, ChatbotServiceError
from app.api.endpoints.token import verify_token, get_tenant_session
from app.config.config import settings

# Configurar logging
logger = logging.getLogger(__name__)

class ChatRequest(SQLModel):
    """Modelo para peticiones de chat"""
    message: str
    session_key: Optional[str] = None
    user_context: Optional[Dict[str, Any]] = None
    reset_conversation: bool = False

class ChatResponse(SQLModel):
    """Modelo para respuestas del chatbot"""
    response: str
    session_key: str

class ChatbotModelCreate(SQLModel):
    """Crear nuevo modelo de IA"""
    name: str
    provider: str
    daily_token_limit: int = 100000
    
class ChatbotModelUpdate(SQLModel):
    """Actualizar modelo de IA"""
    name: Optional[str] = None
    provider: Optional[str] = None
    status: Optional[bool] = None
    daily_token_limit: Optional[int] = None

class ChatbotModelResponse(SQLModel):
    """Response de modelo de IA"""
    id: int
    name: str
    provider: str
    status: bool
    daily_token_limit: int

class ChatbotConfigCreate(SQLModel):
    """Crear configuración desde el dashboard"""
    user_id: int
    api_key: str
    model_id: int
    prompt: str
    temperature: float = 0.7

class ChatbotConfigUpdate(SQLModel):
    """Actualizar configuración desde el dashboard"""
    user_id: Optional[int] = None
    api_key: Optional[str] = None
    model_id: Optional[int] = None
    prompt: Optional[str] = None
    temperature: Optional[float] = None
    status: Optional[bool] = None

class ChatbotConfigResponse(SQLModel):
    """Response al obtener configuración"""
    id: int
    user: UserResponse
    model: ChatbotModelResponse
    prompt: str
    temperature: float
    status: bool
    created_at: datetime
    updated_at: datetime
    
    tokens_used_today: int = 0
    tokens_limit: int
    tokens_remaining: int
    usage_percentage: float

# Crear router
router = APIRouter()

def _calculate_token_usage(
    db: Session,
    api_key: str,
    model_id: int,
    daily_token_limit: int
) -> dict:
    """
    Calcula el uso de tokens para una API key y modelo específico.
    """
    today = datetime.now(timezone.utc).date()
    
    # Buscar el registro de uso de HOY
    usage_record = db.exec(
        select(ChatbotUsage).where(
            ChatbotUsage.api_key == api_key,
            ChatbotUsage.model_id == model_id,
            ChatbotUsage.date == today
        )
    ).first()
    
    tokens_used = usage_record.tokens_used if usage_record else 0
    tokens_remaining = max(0, daily_token_limit - tokens_used)
    usage_percentage = (tokens_used / daily_token_limit * 100) if daily_token_limit > 0 else 0
    
    return {
        "tokens_used_today": tokens_used,
        "tokens_limit": daily_token_limit,
        "tokens_remaining": tokens_remaining,
        "usage_percentage": round(usage_percentage, 2)
    }

# ============================================
# ENDPOINTS DE CHAT
# ============================================

@router.post(
    "/",
    summary="Enviar mensaje al chatbot",
    description="Envía un mensaje al chatbot y recibe una respuesta optimizada según el tipo de usuario.",
    responses={
        200: {"description": "Respuesta del chatbot generada exitosamente"},
        400: {"description": "Solicitud inválida o mensaje vacío"},
        401: {"description": "No autenticado - token inválido o expirado"},
        403: {"description": "No autorizado - chatbot desactivado o no configurado"},
        429: {"description": "Demasiadas solicitudes - rate limit excedido"},
        500: {"description": "Error interno del servidor"}
    }
)
async def send_message(
    chat_request: ChatRequest,
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
) :
    """
    Endpoint principal para interactuar con el chatbot.
    
    Respuestas optimizadas:
    - Website: Solo response + session_key (ligero)
    - Dashboard: Incluye métricas y debugging info (completo)
    """
    source = getattr(current_user, 'source', 'unknown')
    
    logger.info(f"📩 Mensaje recibido - Source: {source}, User: {current_user.email}")
    
    try:
        # Determinar el user_id a usar para obtener la configuración
        if source == "website":
            # Para usuarios del website, buscar el usuario owner/admin del cliente
            owner_user = db.exec(
                select(WepUserModel)
                .where(
                    WepUserModel.client == current_user.client,
                    WepUserModel.email.like("%@shirkasoft.com")
                )
            ).first()
            
            if not owner_user:
                # Alternativa: buscar cualquier usuario del cliente que tenga configuración
                config_user = db.exec(
                    select(WepUserModel)
                    .join(ChatbotConfig, ChatbotConfig.user_id == WepUserModel.id)
                    .where(WepUserModel.client == current_user.client)
                ).first()
                
                if not config_user:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="El chatbot no está configurado para este cliente."
                    )
                user_id = config_user.id
                logger.info(f"🔑 Website usando config de: {config_user.email}")
            else:
                user_id = owner_user.id
                logger.info(f"🔑 Website usando config del owner: {owner_user.email}")
        else:
            # Para usuarios del dashboard, usar su propio ID
            user_id = current_user.id
            logger.info(f"🔑 Dashboard usando config propia: {current_user.email}")
        
        # Inicializar servicio
        chatbot_service = get_chatbot_service(db)
        
        # Procesar el mensaje
        conversation_history = None
        if chat_request.user_context and 'conversation_history' in chat_request.user_context:
            conversation_history = chat_request.user_context['conversation_history']
        
        ai_response, usage_info, session_key = chatbot_service.process_message(
            user_id=user_id,
            user_message=chat_request.message,
            session_key=chat_request.session_key,
            conversation_history=conversation_history
        )
        
        # Generar sugerencias solo si están habilitadas
        suggestions = None
        if getattr(settings, 'ENABLE_SUGGESTIONS', False):
            suggestions = _generate_suggestions(ai_response)
        
        logger.info(f"✅ Respuesta enviada - Tokens: {usage_info.get('total_tokens', 0)}")
        
        # Retornar respuesta optimizada según el tipo de usuario
        if source == "website":
            # Respuesta ligera para website (solo lo esencial)
            return ChatResponse(
                response=ai_response,
                session_key=session_key,
            )
        else:
            # Respuesta completa para dashboard (con métricas)
            return None
        
    except HTTPException:
        raise
    except ChatbotServiceError as e:
        error_msg = str(e)
        
        # Manejar errores específicos
        if "API key de Groq inválida" in error_msg or "sin permisos" in error_msg:
            status_code = status.HTTP_403_FORBIDDEN
            detail = "La configuración del chatbot es inválida. Por favor, actualiza tu API key de Groq en el dashboard."
        elif "desactivado" in error_msg.lower() or "no configurado" in error_msg.lower() or "No se encontró configuración" in error_msg:
            status_code = status.HTTP_403_FORBIDDEN
            detail = "El chatbot no está disponible. Por favor, configúralo desde el dashboard." if source == "dashboard" else "El chatbot no está disponible en este momento."
        elif "mensaje vacío" in error_msg.lower():
            status_code = status.HTTP_400_BAD_REQUEST
            detail = "El mensaje no puede estar vacío"
        elif "modelo" in error_msg.lower() and "no es válido" in error_msg.lower():
            status_code = status.HTTP_400_BAD_REQUEST
            detail = error_msg
        elif "Rate limit" in error_msg or "excedido el límite" in error_msg:
            status_code = status.HTTP_429_TOO_MANY_REQUESTS
            detail = "Has excedido el límite de solicitudes. Por favor, intenta de nuevo en unos momentos."
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            detail = error_msg if getattr(settings, 'SHOW_DETAILED_ERRORS', False) else "Error procesando el mensaje"
        
        raise HTTPException(status_code=status_code, detail=detail)
        
    except Exception as e:
        logger.error(f"❌ Error inesperado: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )


def _generate_suggestions(response_text: str) -> List[str]:
    """
    Genera sugerencias inteligentes basadas en la respuesta del chatbot.
    
    Nota: Actualmente deshabilitado por defecto.
    Para habilitarlo, configurar ENABLE_SUGGESTIONS=true en settings.
    """
    suggestions = []
    response_lower = response_text.lower()
    
    # Sugerencias basadas en palabras clave del negocio
    if any(word in response_lower for word in ["masaje", "spa", "relajación", "terapia"]):
        suggestions.append("Ver tipos de masajes")
    
    if any(word in response_lower for word in ["precio", "costo", "tarifa", "paquete"]):
        suggestions.append("Ver precios y paquetes")
    
    if any(word in response_lower for word in ["agendar", "reservar", "cita", "horario"]):
        suggestions.append("Agendar una cita")
    
    if any(word in response_lower for word in ["ubicación", "dirección", "llegar", "dónde"]):
        suggestions.append("Ver ubicación")
    
    if any(word in response_lower for word in ["contacto", "llamar", "whatsapp", "teléfono"]):
        suggestions.append("Contactar por WhatsApp")
    
    # Si no hay sugerencias específicas, agregar genéricas
    if len(suggestions) == 0:
        suggestions = [
            "Ver servicios disponibles",
            "Agendar una cita",
            "Hablar con un asesor"
        ]
    
    return suggestions[:3]

# ============================================
# ENDPOINTS DE CONFIGURACIÓN
# ============================================

@router.post(
    "/config/",
    status_code=status.HTTP_201_CREATED,
    summary="Crear configuración de chatbot",
    description="Crea una nueva configuración de chatbot para un usuario desde el dashboard"
)
async def create_config(
    config_data: ChatbotConfigCreate,
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
):
    """Crea configuración de chatbot para un usuario."""
    try:
        # Verificar que el user_id existe
        user = db.get(WepUserModel, config_data.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Usuario con id {config_data.user_id} no existe"
            )
        
        # Verificar que no exista ya una configuración para ese usuario
        existing = db.exec(
            select(ChatbotConfig).where(ChatbotConfig.user_id == config_data.user_id)
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe una configuración para el usuario {config_data.user_id}"
            )
        
        # Crear nueva configuración
        new_config = ChatbotConfig(
            user_id=config_data.user_id,
            api_key=hashlib.sha256(config_data.api_key.encode()).hexdigest(),
            model_id=config_data.model_id,
            prompt=config_data.prompt,
            temperature=config_data.temperature,
            status=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        
        db.add(new_config)
        db.commit()
        db.refresh(new_config)
        
        logger.info(f"✅ Configuración creada para user_id: {config_data.user_id}")
        
        return Response(status_code=status.HTTP_201_CREATED)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creando configuración: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la configuración"
        )

@router.get(
    "/config/{user_id}/",
    response_model=ChatbotConfigResponse,
    summary="Obtener configuración por user_id",
    description="Obtiene la configuración del chatbot de un usuario específico"
)
async def get_config(
    user_id: int,
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
):
    """Obtiene configuración de un usuario."""
    try:
        config = db.exec(
            select(ChatbotConfig).where(ChatbotConfig.user_id == user_id)
        ).first()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No existe configuración para el usuario {user_id}"
            )
        
        return ChatbotConfigResponse(
            id=config.id,
            user_id=config.user_id,
            model_id=config.model_id,
            prompt=config.prompt,
            temperature=config.temperature,
            status=config.status,
            created_at=config.created_at,
            updated_at=config.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error obteniendo configuración: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener la configuración"
        )

@router.get("/config/", response_model=List[ChatbotConfigResponse])
async def list_configs(
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
):
    """Lista todas las configuraciones con información de tokens."""
    try:
        # Cargar todas las configs con relaciones
        configs = db.exec(
            select(ChatbotConfig)
            .options(
                selectinload(ChatbotConfig.user),
                selectinload(ChatbotConfig.model)
            )
            .order_by(ChatbotConfig.id)
        ).all()
        
        # ✅ Agregar información de tokens a cada config
        result = []
        for config in configs:
            # Calcular uso de tokens
            token_usage = _calculate_token_usage(
                db=db,
                api_key=config.api_key,
                model_id=config.model_id,
                daily_token_limit=config.model.daily_token_limit
            )
            
            result.append(
                ChatbotConfigResponse(
                    id=config.id,
                    user=config.user,
                    model=config.model,
                    prompt=config.prompt,
                    temperature=config.temperature,
                    status=config.status,
                    created_at=config.created_at,
                    updated_at=config.updated_at,
                    **token_usage
                )
            )
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error listando configuraciones: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al listar configuraciones"
        )

@router.patch("/config/{config_id}/", response_model=ChatbotConfigResponse)
async def update_config(
    config_id: int,
    data: ChatbotConfigUpdate,
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
):
    """Actualiza configuración de un usuario."""
    try:
        config = db.get(ChatbotConfig, config_id)
        
        if not config:
            raise HTTPException(
                status_code=404,
                detail="Configuración de IA no encontrada"
            )
        
        if data.model_id is not None:
            config.model_id = data.model_id
        
        if data.user_id is not None:
            config.user_id = data.user_id
            
        if data.prompt is not None:
            config.prompt = data.prompt
            
        if data.api_key is not None:
            config.api_key = data.api_key
            
        if data.status is not None:
            config.status = data.status

        config.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.merge(config)
        
        return config
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error actualizando configuración: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar la configuración"
        )

@router.delete("/config/{config_id}/", response_model=ChatbotConfigResponse)
async def delete_config(
    config_id: int,
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
):
    """Elimina configuración de un usuario."""

    config = db.get(ChatbotConfig, config_id)
        
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe configuración con id {config_id}"
        )
        
    db.delete(config)
    db.commit()

# ============================================
# ENDPOINTS DE ADMINISTRACIÓN Y MONITOREO
# ============================================

@router.get("/models/", response_model=List[ChatbotModelResponse])
async def get_all_models(
    db: Session = Depends(get_tenant_session),
    active_only: bool = True
):
    """Obtener todos los modelos de IA disponibles"""
    statement = select(ChatbotModel)
    if active_only:
        statement = statement.where(ChatbotModel.status == True)
    
    return db.exec(statement).all()

@router.post("/models/", response_model=ChatbotModelResponse, status_code=status.HTTP_201_CREATED)
async def create_model(
    model_data: ChatbotModelCreate,
    session: Session = Depends(get_tenant_session)
):
    """Crear nuevo modelo de IA"""
    # Verificar si ya existe
    existing = session.exec(
        select(ChatbotModel).where(ChatbotModel.name == model_data.name)
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un modelo con ese nombre."
        )
    
    new_model = ChatbotModel(**model_data.model_dump())
    session.add(new_model)
    session.commit()
    session.merge(new_model)
    
    return new_model

@router.patch("/models/{model_id}/", response_model=ChatbotModelResponse)
async def update_model(
    model_id: int,
    model_data: ChatbotModelUpdate,
    db: Session = Depends(get_tenant_session)
):
    """Actualizar modelo de IA"""
    try:
        model = db.get(ChatbotModel, model_id)
        
        if not model:
            raise HTTPException(
                status_code=404, 
                detail="No se ha encontrado ningún modelo con ese identificador."
            )

        # Obtener solo los campos que se enviaron (exclude_unset=True)
        update_data = model_data.model_dump(exclude_unset=True)
        
        # Si se envía un nombre nuevo, verificar que no exista
        if 'name' in update_data and update_data['name'] != model.name:
            existing = db.exec(
                select(ChatbotModel).where(ChatbotModel.name == update_data['name'])
            ).first()
            
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ya existe un modelo con ese nombre."
                )
        
        # Actualizar campos
        for field, value in update_data.items():
            setattr(model, field, value)
            
        db.add(model)
        db.commit()
        db.refresh(model)
        
        return model
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"No se pudo actualizar el modelo: {str(e)}"
        )

@router.delete("/models/{model_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
    model_id: int,
    db: Session = Depends(get_tenant_session)
):
    """Eliminar modelo de IA"""
    model = db.get(ChatbotModel, model_id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )
    
    # Verificar si hay configs usando este modelo
    configs_using = db.exec(
        select(ChatbotConfig).where(ChatbotConfig.model_id == model_id)
    ).first()
    
    if configs_using:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete model. It's being used by configurations"
        )
    
    db.delete(model)
    db.commit()