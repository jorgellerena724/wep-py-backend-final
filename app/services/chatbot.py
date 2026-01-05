import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from sqlmodel import Session, select, text
from groq import Groq, BadRequestError, APIError

from app.models.wep_chatbot_model import (
    ChatbotConfig, 
    ChatSession, 
    ChatMessage,
    ChatbotUsageStats
)
from app.config.config import settings

logger = logging.getLogger(__name__)


class ChatbotServiceError(Exception):
    """Excepción personalizada para errores del servicio de chatbot"""
    pass


class ChatbotService:
    """
    Servicio principal para manejar el chatbot multitenant.
    
    Responsabilidades:
    1. Gestión de configuración por cliente
    2. Creación y manejo de sesiones
    3. Procesamiento de mensajes con Groq API
    4. Persistencia de conversaciones
    5. Limpieza automática de sesiones expiradas
    """
    
    def __init__(self, db_session: Session):
        logger.info(f"🚀 DEBUG: Inicializando ChatbotService para sesión: {id(db_session)}")
        self.db = db_session
        self.groq_client = None
        try:
            self._initialize_groq_client()
            logger.info("✅ DEBUG: ChatbotService inicializado exitosamente")
        except Exception as e:
            logger.error(f"❌ DEBUG: Error en inicialización del servicio: {str(e)}")
            raise
        
    def _initialize_groq_client(self):
        """Inicializa el cliente de Groq con la API key"""
        try:
            if not settings.GROQ_API_KEY:
                raise ChatbotServiceError("GROQ_API_KEY no configurada en variables de entorno")
            
            self.groq_client = Groq(api_key=settings.GROQ_API_KEY)
            logger.info("✅ Cliente Groq inicializado correctamente")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando cliente Groq: {str(e)}")
            raise ChatbotServiceError(f"No se pudo inicializar el cliente Groq: {str(e)}")
    
    # ============================================
    # MÉTODOS PARA CONFIGURACIÓN
    # ============================================
    
    def get_tenant_config(self, user_id: str) -> ChatbotConfig:
        """
        Obtiene la configuración del chatbot para un tenant específico.
        Si no existe, crea una configuración por defecto.
        """
        try:
            logger.info(f"🔍 DEBUG: Buscando configuración para user_id: {user_id}")
            
            # Buscar configuración existente
            config = self.db.exec(
                select(ChatbotConfig).where(ChatbotConfig.user_id == user_id)
            ).first()
            
            logger.info(f"🔍 DEBUG: Configuración encontrada: {config is not None}")
            
            if not config:
                logger.info(f"⚠️ DEBUG: No se encontró configuración, creando por defecto para {user_id}")
                
                # Crear configuración por defecto con campos que SÍ existen
                config = ChatbotConfig(
                    user_id=user_id,
                    groq_api_key=settings.GROQ_API_KEY,  # Campo requerido que sí existe
                    groq_model=settings.DEFAULT_GROQ_MODEL,
                    prompt=(
                        f"Eres el asistente virtual de {user_id.replace('_', ' ').title()}. "
                        f"Sé amable, profesional y responde en español. "
                        f"Si no sabes algo, dilo honestamente."
                    ),
                    temperature=settings.DEFAULT_TEMPERATURE,
                    is_active=True,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                logger.info(f"✅ DEBUG: Configuración por defecto creada")
                
                self.db.add(config)
                self.db.commit()
                self.db.refresh(config)
                logger.info(f"✅ Configuración por defecto creada para tenant: {user_id}")
            
            return config
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo configuración para {user_id}: {str(e)}")
            raise ChatbotServiceError(f"No se pudo obtener la configuración: {str(e)}")
    
    def update_tenant_config(self, user_id: str, config_data: Dict[str, Any]) -> ChatbotConfig:
        """
        Actualiza la configuración del chatbot para un tenant.
        """
        try:
            config = self.get_tenant_config(user_id)
            
            # Campos permitidos para actualizar
            allowed_fields = [
                'groq_model', 'prompt', 'temperature', 
                'max_tokens', 'max_history', 'session_ttl_minutes',
                'enable_history', 'company_name', 'company_description',
                'contact_info', 'branding', 'welcome_message', 'is_active'
            ]
            
            # Actualizar campos
            for field, value in config_data.items():
                if field in allowed_fields and value is not None:
                    # Manejar campos JSON
                    if field in ['contact_info', 'branding'] and isinstance(value, dict):
                        setattr(config, field, json.dumps(value, ensure_ascii=False))
                    else:
                        setattr(config, field, value)
            
            config.updated_at = datetime.now()
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
            
            logger.info(f"✅ Configuración actualizada para tenant: {user_id}")
            return config
            
        except Exception as e:
            logger.error(f"❌ Error actualizando configuración para {user_id}: {str(e)}")
            raise ChatbotServiceError(f"No se pudo actualizar la configuración: {str(e)}")
    
    # ============================================
    # MÉTODOS PARA SESIONES
    # ============================================
    
    def create_session(
        self,
        user_id: str,
        user_identifier: Optional[str] = None,
        user_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        page_url: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> ChatSession:
        """
        Crea una nueva sesión de chat para un usuario final.
        
        Args:
            user_id: ID del cliente/tenant
            user_identifier: Identificador único del usuario (email, ID, etc.)
            user_ip: Dirección IP del usuario
            user_agent: User-Agent del navegador
            page_url: URL de la página donde inició el chat
            metadata: Metadatos adicionales en formato dict
        
        Returns:
            ChatSession: Sesión creada
        """
        try:
            # Obtener configuración para el TTL
            config = self.get_tenant_config(user_id)
            
            # Generar clave única de sesión
            session_key = f"{user_id}_{uuid.uuid4().hex[:12]}"
            
            # Calcular fecha de expiración
            expires_at = datetime.now() + timedelta(minutes=config.session_ttl_minutes)
            
            # Crear sesión
            session = ChatSession(
                session_key=session_key,
                user_id=user_id,
                user_identifier=user_identifier,
                user_ip=user_ip,
                user_agent=user_agent,
                page_url=page_url,
                metadata=json.dumps(metadata) if metadata else None,
                expires_at=expires_at,
                is_active=True
            )
            
            self.db.add(session)
            self.db.commit()
            self.db.refresh(session)
            
            # Actualizar estadísticas
            self._update_usage_stats(user_id, sessions_increment=1)
            
            logger.info(f"✅ Nueva sesión creada: {session_key} para tenant: {user_id}")
            return session
            
        except Exception as e:
            logger.error(f"❌ Error creando sesión para {user_id}: {str(e)}")
            raise ChatbotServiceError(f"No se pudo crear la sesión: {str(e)}")
    
    def get_active_session(self, session_key: str) -> Optional[ChatSession]:
        """
        Obtiene una sesión activa y no expirada.
        Actualiza la última actividad automáticamente.
        """
        try:
            session = self.db.exec(
                select(ChatSession).where(
                    ChatSession.session_key == session_key,
                    ChatSession.is_active == True,
                    ChatSession.expires_at > datetime.now()
                )
            ).first()
            
            if session:
                # Actualizar última actividad
                session.last_activity = datetime.now()
                
                # Extender expiración según configuración
                config = self.get_tenant_config(session.user_id)
                session.expires_at = datetime.now() + timedelta(minutes=config.session_ttl_minutes)
                
                self.db.add(session)
                self.db.commit()
            
            return session
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo sesión {session_key}: {str(e)}")
            return None
    
    def get_session_messages(
        self, 
        session_key: str, 
        limit: Optional[int] = None
    ) -> List[ChatMessage]:
        """
        Obtiene los mensajes de una sesión, ordenados cronológicamente.
        """
        try:
            query = select(ChatMessage).where(
                ChatMessage.session_key == session_key
            ).order_by(ChatMessage.created_at.asc())
            
            if limit:
                query = query.limit(limit)
            
            messages = self.db.exec(query).all()
            return list(messages) if messages else []
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo mensajes para sesión {session_key}: {str(e)}")
            return []
    
    def get_user_sessions(
        self, 
        user_id: str, 
        user_identifier: str,
        active_only: bool = True
    ) -> List[ChatSession]:
        """
        Obtiene todas las sesiones de un usuario específico.
        """
        try:
            query = select(ChatSession).where(
                ChatSession.user_id == user_id,
                ChatSession.user_identifier == user_identifier
            )
            
            if active_only:
                query = query.where(
                    ChatSession.is_active == True,
                    ChatSession.expires_at > datetime.now()
                )
            
            query = query.order_by(ChatSession.created_at.desc())
            
            sessions = self.db.exec(query).all()
            return list(sessions) if sessions else []
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo sesiones para usuario {user_identifier}: {str(e)}")
            return []
    
    def close_session(self, session_key: str) -> bool:
        """
        Cierra una sesión (marca como inactiva).
        """
        try:
            session = self.get_active_session(session_key)
            if not session:
                return False
            
            session.is_active = False
            self.db.add(session)
            self.db.commit()
            
            # Actualizar estadísticas
            self._update_usage_stats(session.user_id, active_sessions_increment=-1)
            
            logger.info(f"✅ Sesión cerrada: {session_key}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error cerrando sesión {session_key}: {str(e)}")
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """
        Marca como inactivas todas las sesiones expiradas.
        Devuelve el número de sesiones limpiadas.
        """
        try:
            expired_sessions = self.db.exec(
                select(ChatSession).where(
                    ChatSession.is_active == True,
                    ChatSession.expires_at <= datetime.now()
                )
            ).all()
            
            count = 0
            for session in expired_sessions:
                session.is_active = False
                self.db.add(session)
                count += 1
            
            if count > 0:
                self.db.commit()
                logger.info(f"🧹 {count} sesiones expiradas marcadas como inactivas")
            
            return count
            
        except Exception as e:
            logger.error(f"❌ Error limpiando sesiones expiradas: {str(e)}")
            return 0
    
    # ============================================
    # MÉTODOS PARA PROCESAMIENTO DE MENSAJES
    # ============================================
    
    def process_message(
        self,
        user_id: str,
        user_message: str,
        session_key: Optional[str] = None,
        user_context: Optional[Dict[str, Any]] = None,
        create_new_session: bool = True
    ) -> Tuple[str, Dict[str, Any], str]:
        """
        Procesa un mensaje del usuario y devuelve la respuesta del chatbot.
        
        Args:
            user_id: ID del cliente/tenant
            user_message: Mensaje del usuario
            session_key: Clave de sesión existente (opcional)
            user_context: Contexto adicional del usuario (opcional)
            create_new_session: Crear nueva sesión si no existe
        
        Returns:
            tuple: (respuesta_ai, metadatos, session_key)
        """
        logger.info(f"💬 DEBUG: Iniciando process_message para user_id: {user_id}, session_key: {session_key}")
        try:
            # 1. Validar mensaje
            if not user_message or len(user_message.strip()) == 0:
                raise ChatbotServiceError("El mensaje no puede estar vacío")
            
            if len(user_message) > settings.MAX_MESSAGE_LENGTH:
                user_message = user_message[:settings.MAX_MESSAGE_LENGTH]
                logger.warning(f"⚠️ Mensaje truncado a {settings.MAX_MESSAGE_LENGTH} caracteres")
            
            # 2. Obtener o crear sesión
            session = None
            if session_key:
                session = self.get_active_session(session_key)
            
            if not session and create_new_session:
                session = self.create_session(
                    user_id=user_id,
                    user_identifier=user_context.get('email') if user_context else None
                )
                session_key = session.session_key
            elif not session:
                raise ChatbotServiceError("Sesión no encontrada o expirada")
            else:
                session_key = session.session_key
            
            # 3. Obtener configuración del tenant
            config = self.get_tenant_config(user_id)
            
            if not config.is_active:
                raise ChatbotServiceError("El chatbot está desactivado para este cliente")
            
            # 4. Construir mensajes para Groq
            messages = self._build_groq_messages(
                config=config,
                session_key=session_key,
                user_context=user_context,
                user_message=user_message
            )
            
            # 5. Llamar a Groq API
            ai_response, usage_info = self._call_groq_api(
                messages=messages,
                config=config
            )
            
            # 6. Guardar mensajes en la base de datos
            if config.enable_history:
                self._save_message(
                    session_key=session_key,
                    role="user",
                    content=user_message,
                    model_used=None,
                    tokens=usage_info.get('prompt_tokens')
                )
                
                self._save_message(
                    session_key=session_key,
                    role="assistant",
                    content=ai_response,
                    model_used=config.groq_model,
                    tokens=usage_info.get('completion_tokens')
                )
            
            # 7. Actualizar contador de mensajes en la sesión
            session.message_count += 1
            self.db.add(session)
            self.db.commit()
            
            # 8. Actualizar estadísticas
            self._update_usage_stats(
                user_id=user_id,
                messages_increment=1,
                tokens_increment=usage_info.get('total_tokens', 0)
            )
            
            logger.info(
                f"✅ Mensaje procesado - Tenant: {user_id}, "
                f"Sesión: {session_key[:10]}..., "
                f"Tokens: {usage_info.get('total_tokens', 0)}"
            )
            
            return ai_response, usage_info, session_key
            
        except BadRequestError as e:
            logger.error(f"❌ Error de API Groq (BadRequest): {str(e)}")
            raise ChatbotServiceError(f"Error en la solicitud a Groq: {str(e)}")
        except APIError as e:
            logger.error(f"❌ Error de API Groq: {str(e)}")
            raise ChatbotServiceError(f"Error de comunicación con Groq API: {str(e)}")
        except ChatbotServiceError:
            raise
        except Exception as e:
            logger.error(f"❌ Error inesperado procesando mensaje: {str(e)}")
            raise ChatbotServiceError(f"Error interno del servidor: {str(e)}")
    
    def _build_groq_messages(
        self,
        config: ChatbotConfig,
        session_key: str,
        user_context: Optional[Dict[str, Any]],
        user_message: str
    ) -> List[Dict[str, str]]:
        """
        Construye la lista de mensajes para enviar a Groq API.
        """
        messages = []
        
        # 1. Prompt del sistema
        prompt = config.prompt
        
        # Agregar información de la empresa si existe
        if config.company_name:
            prompt += f"\n\nEmpresa: {config.company_name}"
        
        if config.company_description:
            prompt += f"\nDescripción: {config.company_description}"
        
        messages.append({
            "role": "system",
            "content": prompt
        })
        
        # 2. Contexto del usuario (opcional)
        if user_context:
            context_str = json.dumps(user_context, ensure_ascii=False)
            messages.append({
                "role": "system",
                "content": f"Contexto del usuario actual: {context_str}"
            })
        
        # 3. Historial de conversación
        if config.enable_history and config.max_history > 0:
            history_messages = self.get_session_messages(
                session_key=session_key,
                limit=config.max_history
            )
            
            for msg in history_messages:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # 4. Mensaje actual del usuario
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return messages
    
    def _call_groq_api(
        self, 
        messages: List[Dict[str, str]], 
        config: ChatbotConfig
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Llama a la API de Groq y devuelve la respuesta.
        """
        try:
            response = self.groq_client.chat.completions.create(
                messages=messages,
                model=config.groq_model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                stream=False
            )
            
            ai_response = response.choices[0].message.content
            
            usage_info = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "model": config.groq_model,
                "temperature": config.temperature
            }
            
            return ai_response, usage_info
            
        except BadRequestError as e:
            # Intentar con modelo por defecto si falla el específico
            if config.groq_model != settings.DEFAULT_GROQ_MODEL:
                logger.warning(f"⚠️ Modelo {config.groq_model} falló, intentando con modelo por defecto")
                config.groq_model = settings.DEFAULT_GROQ_MODEL
                return self._call_groq_api(messages, config)
            else:
                raise
    
    def _save_message(
        self,
        session_key: str,
        role: str,
        content: str,
        model_used: Optional[str] = None,
        tokens: Optional[int] = None
    ):
        """
        Guarda un mensaje en la base de datos.
        """
        try:
            # Obtener orden del mensaje
            last_order = self.db.exec(
                select(ChatMessage.message_order)
                .where(ChatMessage.session_key == session_key)
                .order_by(ChatMessage.message_order.desc())
                .limit(1)
            ).first()
            
            next_order = (last_order or 0) + 1
            
            message = ChatMessage(
                session_key=session_key,
                role=role,
                content=content,
                tokens=tokens,
                model_used=model_used,
                message_order=next_order
            )
            
            self.db.add(message)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"❌ Error guardando mensaje: {str(e)}")
            # No lanzamos excepción para no interrumpir el flujo principal
    
    # ============================================
    # MÉTODOS PARA ESTADÍSTICAS
    # ============================================
    
    def _update_usage_stats(
        self,
        user_id: str,
        sessions_increment: int = 0,
        active_sessions_increment: int = 0,
        messages_increment: int = 0,
        tokens_increment: int = 0
    ):
        """
        Actualiza las estadísticas de uso del chatbot.
        """
        if not settings.ENABLE_ANALYTICS:
            return
        
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Buscar registro existente para hoy
            stats = self.db.exec(
                select(ChatbotUsageStats).where(
                    ChatbotUsageStats.user_id == user_id,
                    ChatbotUsageStats.date == today
                )
            ).first()
            
            if not stats:
                # Crear nuevo registro
                stats = ChatbotUsageStats(
                    user_id=user_id,
                    date=today,
                    total_sessions=max(sessions_increment, 0),
                    active_sessions=max(active_sessions_increment, 0),
                    total_messages=max(messages_increment, 0),
                    total_tokens=max(tokens_increment, 0)
                )
            else:
                # Actualizar registro existente
                stats.total_sessions += sessions_increment
                stats.active_sessions += active_sessions_increment
                stats.total_messages += messages_increment
                stats.total_tokens += tokens_increment
                stats.updated_at = datetime.now()
            
            self.db.add(stats)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"❌ Error actualizando estadísticas: {str(e)}")
            # Silencioso - no debe interrumpir el flujo principal
    
    def get_usage_stats(
        self, 
        user_id: str, 
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[ChatbotUsageStats]:
        """
        Obtiene estadísticas de uso para un tenant.
        """
        try:
            query = select(ChatbotUsageStats).where(
                ChatbotUsageStats.user_id == user_id
            )
            
            if start_date:
                query = query.where(ChatbotUsageStats.date >= start_date)
            
            if end_date:
                query = query.where(ChatbotUsageStats.date <= end_date)
            
            query = query.order_by(ChatbotUsageStats.date.desc())
            
            stats = self.db.exec(query).all()
            return list(stats) if stats else []
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo estadísticas para {user_id}: {str(e)}")
            return []
    
    # ============================================
    # MÉTODOS AUXILIARES
    # ============================================
    
    def get_welcome_message(self, user_id: str) -> str:
        """
        Obtiene el mensaje de bienvenida personalizado para un tenant.
        """
        try:
            config = self.get_tenant_config(user_id)
            return config.welcome_message or "¡Hola! ¿En qué puedo ayudarte?"
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo mensaje de bienvenida: {str(e)}")
            return "¡Hola! ¿En qué puedo ayudarte?"
    
    def validate_tenant_access(self, user_id: str, session_key: str) -> bool:
        """
        Valida que una sesión pertenezca a un tenant específico.
        """
        try:
            session = self.db.exec(
                select(ChatSession).where(
                    ChatSession.session_key == session_key,
                    ChatSession.user_id == user_id
                )
            ).first()
            
            return session is not None
            
        except Exception as e:
            logger.error(f"❌ Error validando acceso: {str(e)}")
            return False


# Factory para crear instancias del servicio
def get_chatbot_service(db_session: Session) -> ChatbotService:
    """
    Factory function para obtener una instancia del servicio.
    Útil para inyección de dependencias.
    """
    return ChatbotService(db_session)