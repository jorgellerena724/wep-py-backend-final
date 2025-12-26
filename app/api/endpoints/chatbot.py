import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlmodel import Session

# Importaciones internas
from app.models.wep_chatbot_model import (
    ChatRequest,
    ChatResponse,
    SessionInfo,
    ChatbotConfigUpdate
)
from app.services.chatbot import ChatbotService, get_chatbot_service, ChatbotServiceError
from app.api.endpoints.token import verify_token, get_tenant_session  # dependencias existentes
from app.config.chatbot_config import chatbot_settings

# Configurar logging
logger = logging.getLogger(__name__)

# Crear router
router = APIRouter(prefix="/chatbot", tags=["chatbot"])


# ============================================
# MIDDLEWARE Y DEPENDENCIAS ESPECÍFICAS
# ============================================

async def get_current_tenant_id(current_user = Depends(verify_token)) -> str:
    """
    Obtiene el tenant_id del usuario actual.
    Compatible con MockUser (website) y ExtendedUser (dashboard).
    """
    tenant_id = getattr(current_user, 'client', None)
    
    if not tenant_id:
        # Intentar obtener de otras propiedades
        tenant_id = getattr(current_user, 'tenant_id', None)
    
    if not tenant_id:
        logger.error(f"❌ No se pudo obtener tenant_id del usuario: {current_user}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo identificar el cliente/tenant"
        )
    
    logger.debug(f"✅ Tenant ID obtenido: {tenant_id}")
    return tenant_id


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
    current_user = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Endpoint principal para interactuar con el chatbot.
    
    Cada cliente (tenant) tiene su propia configuración y sesiones independientes.
    """
    logger.info(f"📩 Nuevo mensaje recibido - Tenant: {tenant_id}")
    
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
            logger.info(f"🔄 Reiniciando conversación solicitada para tenant: {tenant_id}")
            create_new_session = True
            session_key = None
        elif not session_key:
            create_new_session = True
        
        # 4. Procesar el mensaje
        try:
            ai_response, usage_info, session_key = chatbot_service.process_message(
                tenant_id=tenant_id,
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
                if chatbot_settings.SHOW_DETAILED_ERRORS:
                    detail = error_msg
                else:
                    detail = chatbot_settings.FALLBACK_RESPONSE
                    ai_response = detail
                    usage_info = {}
                    # Intentar crear nueva sesión como fallback
                    try:
                        ai_response, usage_info, session_key = chatbot_service.process_message(
                            tenant_id=tenant_id,
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
        if chatbot_settings.ENABLE_SUGGESTIONS:
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
            f"✅ Respuesta enviada - Tenant: {tenant_id}, "
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
            detail=chatbot_settings.FALLBACK_RESPONSE
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
    current_user = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Obtiene el mensaje de bienvenida personalizado del chatbot."""
    try:
        chatbot_service = get_chatbot_service(db)
        welcome_message = chatbot_service.get_welcome_message(tenant_id)
        
        return {
            "welcome_message": welcome_message,
            "tenant_id": tenant_id,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo mensaje de bienvenida: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo obtener el mensaje de bienvenida"
        )


# ============================================
# ENDPOINTS DE SESIONES
# ============================================

@router.get(
    "/sessions",
    summary="Listar sesiones activas",
    description="Obtiene la lista de sesiones activas para el usuario actual.",
    responses={
        200: {"description": "Lista de sesiones obtenida exitosamente"},
        401: {"description": "No autenticado"},
        500: {"description": "Error interno del servidor"}
    }
)
async def list_sessions(
    active_only: bool = True,
    current_user = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Lista las sesiones del usuario actual."""
    try:
        chatbot_service = get_chatbot_service(db)
        
        # Obtener identificador del usuario
        user_identifier = None
        if hasattr(current_user, 'email') and current_user.email:
            user_identifier = current_user.email
        elif hasattr(current_user, 'id') and current_user.id:
            user_identifier = str(current_user.id)
        
        sessions = chatbot_service.get_user_sessions(
            tenant_id=tenant_id,
            user_identifier=user_identifier,
            active_only=active_only
        )
        
        # Formatear respuesta
        sessions_info = []
        for session in sessions:
            sessions_info.append(SessionInfo(
                session_key=session.session_key,
                tenant_id=session.tenant_id,
                created_at=session.created_at,
                last_activity=session.last_activity,
                expires_at=session.expires_at,
                message_count=session.message_count,
                is_active=session.is_active
            ))
        
        return {
            "user_identifier": user_identifier,
            "total_sessions": len(sessions_info),
            "active_sessions": len([s for s in sessions_info if s.is_active]),
            "sessions": sessions_info
        }
        
    except Exception as e:
        logger.error(f"❌ Error listando sesiones: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron listar las sesiones"
        )


@router.get(
    "/session/{session_key}",
    response_model=SessionInfo,
    summary="Obtener información de una sesión",
    description="Obtiene información detallada de una sesión específica.",
    responses={
        200: {"description": "Información de sesión obtenida exitosamente"},
        400: {"description": "Session_key inválido"},
        401: {"description": "No autenticado"},
        403: {"description": "No autorizado para acceder a esta sesión"},
        404: {"description": "Sesión no encontrada"},
        500: {"description": "Error interno del servidor"}
    }
)
async def get_session(
    session_key: str,
    current_user = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Obtiene información de una sesión específica."""
    try:
        chatbot_service = get_chatbot_service(db)
        
        # Validar que la sesión pertenece al tenant
        if not chatbot_service.validate_tenant_access(tenant_id, session_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a esta sesión"
            )
        
        # Obtener la sesión
        session = chatbot_service.get_active_session(session_key)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sesión no encontrada o expirada"
            )
        
        return SessionInfo(
            session_key=session.session_key,
            tenant_id=session.tenant_id,
            created_at=session.created_at,
            last_activity=session.last_activity,
            expires_at=session.expires_at,
            message_count=session.message_count,
            is_active=session.is_active
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error obteniendo sesión {session_key}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo obtener la información de la sesión"
        )


@router.get(
    "/session/{session_key}/messages",
    summary="Obtener historial de mensajes",
    description="Obtiene el historial de mensajes de una sesión específica.",
    responses={
        200: {"description": "Historial de mensajes obtenido exitosamente"},
        401: {"description": "No autenticado"},
        403: {"description": "No autorizado para acceder a esta sesión"},
        404: {"description": "Sesión no encontrada"},
        500: {"description": "Error interno del servidor"}
    }
)
async def get_session_messages(
    session_key: str,
    limit: int = 50,
    current_user = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Obtiene el historial de mensajes de una sesión."""
    try:
        chatbot_service = get_chatbot_service(db)
        
        # Validar que la sesión pertenece al tenant
        if not chatbot_service.validate_tenant_access(tenant_id, session_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a esta sesión"
            )
        
        # Verificar que la sesión existe
        session = chatbot_service.get_active_session(session_key)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sesión no encontrada o expirada"
            )
        
        # Obtener mensajes
        messages = chatbot_service.get_session_messages(session_key, limit)
        
        # Formatear respuesta
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "tokens": msg.tokens,
                "model_used": msg.model_used,
                "created_at": msg.created_at.isoformat(),
                "order": msg.message_order
            })
        
        return {
            "session_key": session_key,
            "total_messages": len(formatted_messages),
            "messages": formatted_messages
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error obteniendo mensajes de sesión {session_key}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo obtener el historial de mensajes"
        )


@router.delete(
    "/session/{session_key}",
    summary="Cerrar sesión",
    description="Cierra una sesión específica (la marca como inactiva).",
    responses={
        200: {"description": "Sesión cerrada exitosamente"},
        400: {"description": "Session_key inválido"},
        401: {"description": "No autenticado"},
        403: {"description": "No autorizado para cerrar esta sesión"},
        404: {"description": "Sesión no encontrada"},
        500: {"description": "Error interno del servidor"}
    }
)
async def close_session(
    session_key: str,
    background_tasks: BackgroundTasks,
    current_user = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Cierra una sesión específica."""
    try:
        chatbot_service = get_chatbot_service(db)
        
        # Validar que la sesión pertenece al tenant
        if not chatbot_service.validate_tenant_access(tenant_id, session_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No puedes cerrar esta sesión"
            )
        
        # Cerrar sesión
        closed = chatbot_service.close_session(session_key)
        if not closed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sesión no encontrada"
            )
        
        # Programar limpieza
        schedule_cleanup(background_tasks, chatbot_service)
        
        return {
            "message": "Sesión cerrada correctamente",
            "session_key": session_key,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error cerrando sesión {session_key}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo cerrar la sesión"
        )


# ============================================
# ENDPOINTS DE CONFIGURACIÓN
# ============================================

@router.get(
    "/config",
    summary="Obtener configuración del chatbot",
    description="Obtiene la configuración actual del chatbot para el cliente actual.",
    responses={
        200: {"description": "Configuración obtenida exitosamente"},
        401: {"description": "No autenticado"},
        500: {"description": "Error interno del servidor"}
    }
)
async def get_configuration(
    current_user = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Obtiene la configuración del chatbot para el tenant actual."""
    try:
        chatbot_service = get_chatbot_service(db)
        config = chatbot_service.get_tenant_config(tenant_id)
        
        # Formatear respuesta
        response = {
            "tenant_id": config.tenant_id,
            "groq_model": config.groq_model,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "max_history": config.max_history,
            "session_ttl_minutes": config.session_ttl_minutes,
            "enable_history": config.enable_history,
            "company_name": config.company_name,
            "company_description": config.company_description,
            "welcome_message": config.welcome_message,
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat(),
            "updated_at": config.updated_at.isoformat()
        }
        
        # Agregar campos JSON parseados
        if config.contact_info:
            try:
                import json
                response["contact_info"] = json.loads(config.contact_info)
            except:
                response["contact_info"] = config.contact_info
        
        if config.branding:
            try:
                import json
                response["branding"] = json.loads(config.branding)
            except:
                response["branding"] = config.branding
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo configuración: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo obtener la configuración"
        )


@router.put(
    "/config",
    summary="Actualizar configuración del chatbot",
    description="Actualiza la configuración del chatbot para el cliente actual.",
    responses={
        200: {"description": "Configuración actualizada exitosamente"},
        400: {"description": "Datos de configuración inválidos"},
        401: {"description": "No autenticado"},
        403: {"description": "No autorizado para actualizar configuración"},
        500: {"description": "Error interno del servidor"}
    }
)
async def update_configuration(
    config_update: ChatbotConfigUpdate,
    current_user = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Actualiza la configuración del chatbot."""
    try:
        # Verificar permisos (solo usuarios del dashboard pueden actualizar)
        user_source = getattr(current_user, 'source', 'unknown')
        if user_source != 'dashboard':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo los usuarios del dashboard pueden actualizar la configuración"
            )
        
        chatbot_service = get_chatbot_service(db)
        
        # Convertir a dict y eliminar campos None
        update_data = config_update.dict(exclude_none=True)
        
        # Actualizar configuración
        updated_config = chatbot_service.update_tenant_config(tenant_id, update_data)
        
        return {
            "message": "Configuración actualizada correctamente",
            "tenant_id": updated_config.tenant_id,
            "updated_fields": list(update_data.keys()),
            "updated_at": updated_config.updated_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error actualizando configuración: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo actualizar la configuración"
        )


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
    current_user = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
    tenant_id: str = Depends(get_current_tenant_id)
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
        stats = chatbot_service.get_usage_stats(tenant_id, start_date, end_date)
        
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
            "tenant_id": tenant_id,
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
    current_user = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
    tenant_id: str = Depends(get_current_tenant_id)
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
            "tenant_id": tenant_id,
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
    current_user = Depends(verify_token),
    db: Session = Depends(get_tenant_session),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Endpoint de health check para el chatbot."""
    try:
        chatbot_service = get_chatbot_service(db)
        
        # 1. Verificar configuración del tenant
        config = chatbot_service.get_tenant_config(tenant_id)
        
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
            tenant_id=tenant_id,
            user_identifier=None,
            active_only=True
        ))
        
        return {
            "status": "healthy",
            "tenant_id": tenant_id,
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
    if not chatbot_settings.ENABLE_SUGGESTIONS:
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

@router.exception_handler(ChatbotServiceError)
async def chatbot_service_exception_handler(request, exc):
    """Manejador de excepciones específicas del servicio de chatbot."""
    logger.error(f"❌ ChatbotServiceError: {str(exc)}")
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Error del servicio de chatbot",
            "detail": str(exc) if chatbot_settings.SHOW_DETAILED_ERRORS else "Error interno del chatbot"
        }
    )


@router.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Manejador de excepciones generales."""
    logger.error(f"❌ Excepción no manejada en chatbot: {str(exc)}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Error interno del servidor",
            "detail": chatbot_settings.FALLBACK_RESPONSE
        }
    )


# Exportar router
__all__ = ["router"]