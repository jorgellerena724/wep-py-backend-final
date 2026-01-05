import logging
from datetime import datetime, timezone
from sqlalchemy.orm import selectinload
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel, Session, select
from app.api.endpoints.user import UserResponse
from app.models.wep_chatbot_model import (
    ChatRequest,
    ChatResponse,
    ChatbotConfig,
    ChatbotModel,
    SessionInfo,
)
from app.models.wep_user_model import WepUserModel
from app.services.chatbot import ChatbotService, get_chatbot_service, ChatbotServiceError
from app.api.endpoints.token import verify_token, get_tenant_session
from app.config.config import settings

# Configurar logging
logger = logging.getLogger(__name__)

class ChatbotModelCreate(SQLModel):
    """Crear nuevo modelo de IA"""
    name: str
    provider: str
    
class ChatbotModelUpdate(SQLModel):
    """Crear nuevo modelo de IA"""
    name: Optional[str] = None
    provider: Optional[str] = None
    status: Optional[bool] = None

class ChatbotModelResponse(SQLModel):
    """Response de modelo de IA"""
    id: int
    name: str
    provider: str
    status: bool

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

# Crear router
router = APIRouter()

# ============================================
# MIDDLEWARE Y DEPENDENCIAS ESPECÍFICAS
# ============================================

def schedule_cleanup(background_tasks: BackgroundTasks, chatbot_service: ChatbotService):
    """
    Programa la limpieza de sesiones expiradas en segundo plano.
    """
    def cleanup_task():
        try:
            cleaned = chatbot_service.cleanup_expired_sessions()
            if cleaned > 0:
                logger.info(f"🧹 Tarea de limpieza: {cleaned} sesiones expiradas eliminadas")
        except Exception as e:
            logger.error(f"❌ Error en tarea de limpieza: {str(e)}")
    
    background_tasks.add_task(cleanup_task)


# ============================================
# ENDPOINTS DE CHAT
# ============================================

@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Enviar mensaje al chatbot",
    description="""
    Envía un mensaje al chatbot y recibe una respuesta.
    
    - Si no se proporciona `session_key`, se crea una nueva sesión
    - Las sesiones expiran automáticamente después de un tiempo de inactividad
    - El historial de conversación se mantiene dentro de la sesión
    - Se usa la configuración específica del cliente (tenant)
    """,
    responses={
        200: {"description": "Respuesta del chatbot generada exitosamente"},
        400: {"description": "Solicitud inválida o mensaje vacío"},
        401: {"description": "No autenticado - token inválido o expirado"},
        403: {"description": "No autorizado - chatbot desactivado para este cliente"},
        500: {"description": "Error interno del servidor"}
    }
)
async def send_message(
    request: Request,
    chat_request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
):
    """
    Endpoint principal para interactuar con el chatbot.
    
    Cada cliente (tenant) tiene su propia configuración y sesiones independientes.
    """
    logger.info(f"📩 Nuevo mensaje recibido - Tenant: {current_user.client}")
    
    try:
        # 1. Inicializar servicio
        chatbot_service = get_chatbot_service(db)
        
        # 2. Extraer información del request para contexto
        user_context = chat_request.user_context or {}
        
        # Agregar información del usuario si está disponible
        if hasattr(current_user, 'email') and current_user.email:
            user_context['user_email'] = current_user.email
        
        if hasattr(current_user, 'full_name') and current_user.full_name:
            user_context['user_name'] = current_user.full_name
        
        # Agregar información de la solicitud HTTP
        user_context.update({
            'user_ip': request.client.host if request.client else None,
            'user_agent': request.headers.get("user-agent"),
            'source': getattr(current_user, 'source', 'unknown'),
            'timestamp': datetime.now().isoformat()
        })
        
        # 3. Determinar si crear nueva sesión
        create_new_session = False
        session_key = chat_request.session_key
        
        if chat_request.reset_conversation:
            logger.info(f"🔄 Reiniciando conversación solicitada para tenant: {current_user.client}")
            create_new_session = True
            session_key = None
        elif not session_key:
            create_new_session = True
        
        # 4. Procesar el mensaje
        try:
            ai_response, usage_info, session_key = chatbot_service.process_message(
                tenant_id=current_user.id,
                user_message=chat_request.message,
                session_key=session_key,
                user_context=user_context,
                create_new_session=create_new_session
            )
            
        except ChatbotServiceError as e:
            error_msg = str(e)
            
            # Manejar errores específicos
            if "desactivado" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="El chatbot está desactivado para este cliente"
                )
            elif "sesión no encontrada" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La sesión ha expirado. Por favor, inicia una nueva conversación."
                )
            else:
                # Error genérico
                if settings.SHOW_DETAILED_ERRORS:
                    detail = error_msg
                else:
                    detail = settings.FALLBACK_RESPONSE
                    ai_response = detail
                    usage_info = {}
                    # Intentar crear nueva sesión como fallback
                    try:
                        ai_response, usage_info, session_key = chatbot_service.process_message(
                            tenant_id=current_user.id,
                            user_message=chat_request.message,
                            session_key=None,
                            user_context=user_context,
                            create_new_session=True
                        )
                    except:
                        pass  # Usar el fallback ya establecido
        
        # 5. Programar limpieza en segundo plano
        schedule_cleanup(background_tasks, chatbot_service)
        
        # 6. Generar sugerencias si está habilitado
        suggestions = None
        if settings.ENABLE_SUGGESTIONS:
            suggestions = _generate_suggestions(ai_response)
        
        # 7. Crear respuesta
        response = ChatResponse(
            response=ai_response,
            session_key=session_key,
            model_used=usage_info.get('model'),
            usage={
                "prompt_tokens": usage_info.get('prompt_tokens', 0),
                "completion_tokens": usage_info.get('completion_tokens', 0),
                "total_tokens": usage_info.get('total_tokens', 0)
            } if usage_info else None,
            suggestions=suggestions
        )
        
        logger.info(
            f"✅ Respuesta enviada - Tenant: {current_user.id}, "
            f"Sesión: {session_key[:10]}..., "
            f"Tokens: {response.usage.get('total_tokens', 0) if response.usage else 0}"
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error inesperado en endpoint /chat: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=settings.FALLBACK_RESPONSE
        )

@router.get(
    "/welcome",
    summary="Obtener mensaje de bienvenida",
    description="Devuelve el mensaje de bienvenida personalizado del chatbot para el cliente actual.",
    responses={
        200: {"description": "Mensaje de bienvenida obtenido exitosamente"},
        401: {"description": "No autenticado"},
        500: {"description": "Error interno del servidor"}
    }
)
async def get_welcome_message(
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
):
    """Obtiene el mensaje de bienvenida personalizado del chatbot."""
    try:
        chatbot_service = get_chatbot_service(db)
        welcome_message = chatbot_service.get_welcome_message(current_user.id)
        
        return {
            "welcome_message": welcome_message,
            "tenant_id": current_user.id,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo mensaje de bienvenida: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo obtener el mensaje de bienvenida"
        )

# ============================================
# ENDPOINTS DE CONFIGURACIÓN
# ============================================

@router.post(
    "/config/",
    response_model=ChatbotConfigResponse,
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
            api_key=config_data.api_key,
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
        
        return ChatbotConfigResponse(
            id=new_config.id,
            user_id=new_config.user_id,
            model_id=new_config.model_id,
            prompt=new_config.prompt,
            temperature=new_config.temperature,
            status=new_config.status,
            created_at=new_config.created_at,
            updated_at=new_config.updated_at
        )
        
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
    """Lista todas las configuraciones."""
    try:
        
        return db.exec(select(ChatbotConfig).options(selectinload(ChatbotConfig.user),selectinload(ChatbotConfig.model)).order_by(ChatbotConfig.id)).all()
        
    except Exception as e:
        logger.error(f"❌ Error listando configuraciones: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al listar configuraciones"
        )

@router.patch("/config/{config_id}/", response_model=ChatbotConfigResponse)
async def update_config(
    config_id: int,
    config_update: ChatbotConfigUpdate,
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
        
        if config_update.model_id is not None:
            config.model_id = config_update.model_id
        
        if config_update.user_id is not None:
            config.user_id = config_update.user_id
            
        if config_update.prompt is not None:
            config.prompt = config_update.prompt
            
        if config_update.api_key is not None:
            config.api_key = config_update.api_key
            
        if config_update.status is not None:
            config.status = config_update.status

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

@router.delete("/config/{user_id}/", response_model=ChatbotConfigResponse)
async def delete_config(
    user_id: int,
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
):
    """Elimina configuración de un usuario."""
    try:
        config = db.exec(
            select(ChatbotConfig).where(ChatbotConfig.user_id == user_id)
        ).first()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No existe configuración para el usuario {user_id}"
            )
        
        db.delete(config)
        db.commit()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error eliminando configuración: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar la configuración"
        )

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
    session: Session = Depends(get_tenant_session)
):
    """Eliminar modelo de IA"""
    model = session.get(ChatbotModel, model_id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found"
        )
    
    # Verificar si hay configs usando este modelo
    configs_using = session.exec(
        select(ChatbotConfig).where(ChatbotConfig.model_id == model_id)
    ).first()
    
    if configs_using:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete model. It's being used by configurations"
        )
    
    session.delete(model)
    session.commit()

# ============================================
# ENDPOINTS DE ADMINISTRACIÓN Y MONITOREO
# ============================================

@router.get(
    "/stats",
    summary="Obtener estadísticas de uso",
    description="Obtiene estadísticas de uso del chatbot para el cliente actual.",
    responses={
        200: {"description": "Estadísticas obtenidas exitosamente"},
        401: {"description": "No autenticado"},
        403: {"description": "No autorizado para ver estadísticas"},
        500: {"description": "Error interno del servidor"}
    }
)
async def get_usage_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
):
    """Obtiene estadísticas de uso del chatbot."""
    try:
        # Verificar permisos (solo dashboard)
        user_source = getattr(current_user, 'source', 'unknown')
        if user_source != 'dashboard':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo los usuarios del dashboard pueden ver estadísticas"
            )
        
        chatbot_service = get_chatbot_service(db)
        
        # Obtener estadísticas
        stats = chatbot_service.get_usage_stats(current_user.id, start_date, end_date)
        
        # Formatear respuesta
        formatted_stats = []
        total_sessions = 0
        total_messages = 0
        total_tokens = 0
        
        for stat in stats:
            formatted_stats.append({
                "date": stat.date,
                "total_sessions": stat.total_sessions,
                "active_sessions": stat.active_sessions,
                "total_messages": stat.total_messages,
                "total_tokens": stat.total_tokens,
                "estimated_cost": stat.estimated_cost,
                "updated_at": stat.updated_at.isoformat()
            })
            
            total_sessions += stat.total_sessions
            total_messages += stat.total_messages
            total_tokens += stat.total_tokens
        
        return {
            "tenant_id": current_user.id,
            "period": {
                "start_date": start_date,
                "end_date": end_date
            },
            "totals": {
                "total_sessions": total_sessions,
                "total_messages": total_messages,
                "total_tokens": total_tokens
            },
            "daily_stats": formatted_stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error obteniendo estadísticas: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron obtener las estadísticas"
        )


@router.post(
    "/cleanup",
    summary="Forzar limpieza de sesiones",
    description="Fuerza la limpieza de sesiones expiradas (normalmente se hace automáticamente).",
    responses={
        200: {"description": "Limpieza ejecutada exitosamente"},
        401: {"description": "No autenticado"},
        403: {"description": "No autorizado para ejecutar limpieza"},
        500: {"description": "Error interno del servidor"}
    }
)
async def force_cleanup(
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
):
    """Fuerza la limpieza de sesiones expiradas."""
    try:
        # Verificar permisos (solo dashboard)
        user_source = getattr(current_user, 'source', 'unknown')
        if user_source != 'dashboard':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo los usuarios del dashboard pueden forzar limpieza"
            )
        
        chatbot_service = get_chatbot_service(db)
        cleaned = chatbot_service.cleanup_expired_sessions()
        
        return {
            "message": f"Limpieza completada. {cleaned} sesiones expiradas eliminadas.",
            "tenant_id": current_user.id,
            "sessions_cleaned": cleaned,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error forzando limpieza: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo ejecutar la limpieza"
        )


@router.get(
    "/health",
    summary="Verificar salud del chatbot",
    description="Verifica que el chatbot esté funcionando correctamente.",
    responses={
        200: {"description": "Chatbot funcionando correctamente"},
        500: {"description": "Problemas detectados en el chatbot"}
    }
)
async def health_check(
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
):
    """Endpoint de health check para el chatbot."""
    try:
        chatbot_service = get_chatbot_service(db)
        
        # 1. Verificar configuración del tenant
        config = chatbot_service.get_tenant_config(current_user.id)
        
        # 2. Verificar conexión con Groq (puede ser liviano)
        try:
            # Intentar una operación simple de Groq
            models = chatbot_service.groq_client.models.list()
            groq_status = "connected"
            available_models = len(models.data) if hasattr(models, 'data') else "unknown"
        except Exception as e:
            groq_status = f"error: {str(e)}"
            available_models = 0
        
        # 3. Obtener estadísticas básicas
        active_sessions = len(chatbot_service.get_user_sessions(
            tenant_id=current_user.id,
            user_identifier=None,
            active_only=True
        ))
        
        return {
            "status": "healthy",
            "tenant_id": current_user.id,
            "chatbot_active": config.is_active,
            "groq_status": groq_status,
            "available_models": available_models,
            "active_sessions": active_sessions,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Health check falló: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chatbot no está completamente operacional: {str(e)}"
        )


# ============================================
# FUNCIONES AUXILIARES
# ============================================

def _generate_suggestions(response_text: str) -> List[str]:
    """
    Genera sugerencias basadas en la respuesta del chatbot.
    Esta es una implementación básica que puedes mejorar.
    """
    if not settings.ENABLE_SUGGESTIONS:
        return None
    
    suggestions = []
    response_lower = response_text.lower()
    
    # Sugerencias basadas en contenido común
    if any(word in response_lower for word in ["producto", "catálogo", "compra"]):
        suggestions.append("Ver productos similares")
    
    if any(word in response_lower for word in ["precio", "costo", "valor"]):
        suggestions.append("Consultar precios detallados")
    
    if any(word in response_lower for word in ["horario", "contacto", "llamar"]):
        suggestions.append("Contactar con un agente")
    
    if any(word in response_lower for word in ["problema", "error", "soporte"]):
        suggestions.append("Abrir ticket de soporte")
    
    # Sugerencias genéricas
    if len(suggestions) < 3:
        generic_suggestions = [
            "¿Puedes explicarlo de otra manera?",
            "Necesito más información",
            "¿Tienes alguna recomendación?"
        ]
        suggestions.extend(generic_suggestions[:3 - len(suggestions)])
    
    return suggestions[:3]  # Máximo 3 sugerencias


# ============================================
# MANEJO DE EXCEPCIONES GLOBAL
# ============================================

async def chatbot_service_exception_handler(request, exc):
    """Manejador de excepciones específicas del servicio de chatbot."""
    logger.error(f"❌ ChatbotServiceError: {str(exc)}")
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Error del servicio de chatbot",
            "detail": str(exc) if settings.SHOW_DETAILED_ERRORS else "Error interno del chatbot"
        }
    )


async def general_exception_handler(request, exc):
    """Manejador de excepciones generales."""
    logger.error(f"❌ Excepción no manejada en chatbot: {str(exc)}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Error interno del servidor",
            "detail": settings.FALLBACK_RESPONSE
        }
    )