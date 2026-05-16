from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Tuple, Any
from sqlmodel import Session, func, select
from sqlalchemy.orm import selectinload
from groq import Groq, BadRequestError, APIError, RateLimitError
from cerebras.cloud.sdk import Cerebras
from app.models.wep_chatbot_model import ChatbotConfig, ChatbotModel, ChatbotUsage
from app.config.config import settings

logger = logging.getLogger(__name__)


class ChatbotServiceError(Exception):
    """Excepción personalizada para errores del servicio de chatbot"""
    pass


class ChatbotService:
    """
    Servicio simplificado para manejar el chatbot.
    Soporta múltiples proveedores: Groq y Cerebras.
    No gestiona sesiones - eso lo hace el frontend.
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.groq_clients = {}      # Cache de clientes Groq por usuario
        self.cerebras_clients = {}  # Cache de clientes Cerebras por usuario
        logger.info("✅ ChatbotService inicializado con soporte para Groq y Cerebras")
    
    # ---------- Clientes por proveedor ----------
    def _get_groq_client(self, user_id: int, api_key: str) -> Groq:
        """Obtiene o crea un cliente de Groq para un usuario específico."""
        cache_key = f"{user_id}_{api_key[:8]}"
        try:
            if cache_key in self.groq_clients:
                return self.groq_clients[cache_key]
            
            if not api_key:
                raise ChatbotServiceError("API key de Groq no configurada")
            
            groq_client = Groq(api_key=api_key)
            self.groq_clients[cache_key] = groq_client
            logger.info(f"✅ Cliente Groq creado para usuario {user_id}")
            return groq_client
        except Exception as e:
            logger.error(f"❌ Error creando cliente Groq: {str(e)}")
            raise ChatbotServiceError(f"No se pudo inicializar el cliente Groq: {str(e)}")
    
    def _get_cerebras_client(self, user_id: int, api_key: str) -> Cerebras:
        """Obtiene o crea un cliente de Cerebras para un usuario específico."""
        cache_key = f"{user_id}_{api_key[:8]}"
        try:
            if cache_key in self.cerebras_clients:
                return self.cerebras_clients[cache_key]
            
            if not api_key:
                raise ChatbotServiceError("API key de Cerebras no configurada")
            
            cerebras_client = Cerebras(api_key=api_key)
            self.cerebras_clients[cache_key] = cerebras_client
            logger.info(f"✅ Cliente Cerebras creado para usuario {user_id}")
            return cerebras_client
        except Exception as e:
            logger.error(f"❌ Error creando cliente Cerebras: {str(e)}")
            raise ChatbotServiceError(f"No se pudo inicializar el cliente Cerebras: {str(e)}")
    
    # ---------- Configuración ----------
    def _get_user_config(self, user_id: int) -> Optional[ChatbotConfig]:
        """Obtiene la configuración del chatbot para un usuario desde la BD."""
        try:
            logger.info(f"🔍 Buscando configuración para user_id: {user_id}")
            if not isinstance(user_id, int):
                try:
                    user_id = int(user_id)
                except (ValueError, TypeError):
                    logger.error(f"❌ user_id inválido: {user_id}")
                    return None
            
            config = self.db.exec(
                select(ChatbotConfig)
                .where(ChatbotConfig.user_id == user_id)
            ).first()
            
            if config:
                models_count = len(config.models_list)
                logger.info(f"✅ Configuración encontrada - Modelos: {models_count}")
            else:
                logger.warning(f"⚠️ No se encontró configuración para user_id: {user_id}")
            return config
        except Exception as e:
            logger.error(f"❌ Error obteniendo configuración: {str(e)}")
            return None
    
# ---------- Fallback: obtener mejor modelo por provider ----------
    def _get_best_model(self, config: ChatbotConfig) -> Optional[Dict[str, Any]]:
        """
        Selecciona el mejor modelo por provider basado en tokens disponibles.
        Para cada provider, busca el modelo con más tokens remaining.
        """
        today_date = datetime.now(timezone.utc).date()
        
        best_provider = None
        best_model = None
        best_tokens_remaining = -1
        
        for provider_item in config.models_list:
            provider = provider_item.get("provider", "").lower()
            api_key = provider_item.get("api_key", "")
            
            if not provider:
                continue
            
            # Buscar modelos activos de este provider
            models = self.db.exec(
                select(ChatbotModel).where(
                    ChatbotModel.provider.ilike(provider),
                    ChatbotModel.status == True
                )
            ).all()
            
            if not models:
                logger.warning(f"⚠️ No hay modelos activos para provider: {provider}")
                continue
            
            #Seleccionar el modelo con más tokens disponibles
            for model in models:
                usage_record = self.db.exec(
                    select(ChatbotUsage).where(
                        ChatbotUsage.api_key == api_key,
                        ChatbotUsage.model_id == model.id,
                        func.date(ChatbotUsage.date) == today_date
                    )
                ).first()
                
                tokens_used = usage_record.tokens_used if usage_record else 0
                tokens_remaining = model.daily_token_limit - tokens_used
                
                if tokens_remaining > best_tokens_remaining:
                    best_tokens_remaining = tokens_remaining
                    best_model = model
                    best_provider = provider
        
        if best_model:
            logger.info(f"🎯 Mejor modelo: {best_model.name} (provider: {best_provider}, tokens: {best_tokens_remaining})")
        
        if best_model and best_provider:
            api_key = next((item.get("api_key", "") for item in config.models_list if item.get("provider", "").lower() == best_provider), "")
            return {
                "model": best_model,
                "provider": best_provider,
                "api_key": api_key,
                "tokens_remaining": best_tokens_remaining
            }
        
        return None
    
# ---------- Procesamiento principal ----------
    def process_message(
        self,
        user_id: int,
        user_message: str,
        session_key: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[str, Dict[str, Any], str]:
        """
        Procesa un mensaje del usuario con soporte para fallback automático.
        1. Selecciona el mejor modelo por tokens disponibles
        2. Si falla (429 o error), triede el siguiente modelo
        """
        logger.info(f"💬 Procesando mensaje para user_id: {user_id}")
        
        try:
            if not user_message or len(user_message.strip()) == 0:
                raise ChatbotServiceError("El mensaje no puede estar vacío")
            
            max_length = getattr(settings, 'MAX_MESSAGE_LENGTH', 2000)
            if len(user_message) > max_length:
                user_message = user_message[:max_length]
                logger.warning(f"⚠️ Mensaje truncado a {max_length} caracteres")
            
            if not session_key:
                import uuid
                session_key = f"session_{user_id}_{uuid.uuid4().hex[:8]}"
                logger.info(f"🆕 Nueva sesión: {session_key}")
            
            config = self._get_user_config(user_id)
            if not config:
                raise ChatbotServiceError(
                    "No se encontró configuración de chatbot. "
                    "Por favor, configura el chatbot desde el dashboard."
                )
            if not config.status:
                raise ChatbotServiceError("El chatbot está desactivado")
            
            if not config.models_list:
                raise ChatbotServiceError("No hay modelos configurados")
            
            return self._process_with_fallback(
                            config=config,
                            user_message=user_message,
                            conversation_history=conversation_history,
                            session_key=session_key,
                            user_id=user_id
                        )

        except BadRequestError as e:
            logger.error(f"❌ Error de API Groq (BadRequest): {str(e)}")
            raise ChatbotServiceError(f"Error en la solicitud a Groq: {str(e)}")
        except APIError as e:
            logger.error(f"❌ Error de API Groq: {str(e)}")
            raise ChatbotServiceError(f"Error de comunicación con Groq API: {str(e)}")
        except ChatbotServiceError:
            raise
        except Exception as e:
            logger.error(f"❌ Error inesperado: {str(e)}", exc_info=True)
            raise ChatbotServiceError(f"Error interno del servidor: {str(e)}")
    
    # ---------- Fallback: procesamiento con retry ----------
    def _process_with_fallback(
        self,
        config: ChatbotConfig,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        session_key: str = None,
        user_id: int = 0
    ) -> Tuple[str, Dict[str, Any], str]:
        """
        Procesa el mensaje con fallback automático.
        Si un modelo falla o se queda sin tokens, prueba el siguiente.
        """
        models_list = config.models_list.copy()
        last_error = None
        
        for attempt in range(len(models_list)):
            best = self._get_best_model(config)
            if not best:
                raise ChatbotServiceError("No hay modelos disponibles con tokens")
            
            model = best["model"]
            api_key = best["api_key"]
            provider = model.provider.lower()
            model_name = model.name
            
            logger.info(f"🎯 Intentando modelo: {model_name} ({provider})")
            
            try:
                return self._call_model(
                    config=config,
                    user_message=user_message,
                    conversation_history=conversation_history,
                    session_key=session_key,
                    user_id=user_id,
                    model=model,
                    api_key=api_key,
                    provider=provider,
                    model_name=model_name
                )
            except (RateLimitError, APIError) as e:
                error_msg = str(e)
                if "429" in error_msg or "rate" in error_msg.lower() or "Too Many Requests" in error_msg:
                    logger.warning(f"⚠️ Rate limit en {model_name}, probando siguiente...")
                    last_error = f"Rate limit excedido para {model_name}"
                    continue
                else:
                    logger.warning(f"⚠️ Error de API en {model_name}: {error_msg}, probando siguiente...")
                    last_error = error_msg
                    continue
            except ChatbotServiceError as e:
                error_msg = str(e)
                if "límite diario" in error_msg.lower() or "tokens" in error_msg.lower():
                    logger.warning(f"⚠️ Sin tokens en {model_name}, probando siguiente...")
                    last_error = error_msg
                    continue
                raise
        
        raise ChatbotServiceError(f"No hay modelos disponibles: {last_error}")
    
    def _call_model(
        self,
        config: ChatbotConfig,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]],
        session_key: str,
        user_id: int,
        model: ChatbotModel,
        api_key: str,
        provider: str,
        model_name: str
    ) -> Tuple[str, Dict[str, Any], str]:
        """Llama al proveedor específico y actualiza el uso."""
        today_date = datetime.now(timezone.utc).date()
        today_datetime = datetime.combine(today_date, datetime.min.time())
        
        usage_record = self.db.exec(
            select(ChatbotUsage).where(
                ChatbotUsage.api_key == api_key,
                ChatbotUsage.model_id == model.id,
                func.date(ChatbotUsage.date) == today_date
            )
        ).first()
        
        if not usage_record:
            usage_record = ChatbotUsage(
                user_id=user_id,
                api_key=api_key,
                model_id=model.id,
                date=today_datetime,
                tokens_used=0
            )
            self.db.add(usage_record)
            self.db.commit()
            self.db.refresh(usage_record)
        
        model_limit = model.daily_token_limit
        if usage_record.tokens_used >= model_limit:
            raise ChatbotServiceError(f"Límite diario excedido para el modelo {model_name}")
        
        messages = self._build_messages(config, user_message, conversation_history)
        
        if provider == "groq":
            ai_response, usage_info = self._call_groq_api(
                user_id=user_id,
                api_key=api_key,
                messages=messages,
                config=config,
                model_name=model_name
            )
        elif provider == "cerebras":
            ai_response, usage_info = self._call_cerebras_api(
                user_id=user_id,
                api_key=api_key,
                messages=messages,
                config=config,
                model_name=model_name
            )
        else:
            raise ChatbotServiceError(f"Proveedor no soportado: {provider}")
        
        usage_record.tokens_used += usage_info.get('total_tokens', 0)
        usage_record.date = today_datetime
        self.db.add(usage_record)
        self.db.commit()
        
        logger.info(f"✅ Procesado con {model_name}, Tokens: {usage_info.get('total_tokens', 0)}")
        return ai_response, usage_info, session_key
    
    # ---------- Construcción de mensajes ----------
    def _build_messages(
        self,
        config: ChatbotConfig,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, str]]:
        """Construye la lista de mensajes para enviar a cualquier API (formato estándar)."""
        messages = []
        messages.append({"role": "system", "content": config.prompt})
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})
        logger.info(f"📝 Construidos {len(messages)} mensajes")
        return messages
    
    # ---------- Llamadas específicas a APIs ----------
    def _call_groq_api(
        self,
        user_id: int,
        api_key: str,
        messages: List[Dict[str, str]], 
        config: ChatbotConfig,
        model_name: str
    ) -> Tuple[str, Dict[str, Any]]:
        """Llama a la API de Groq usando la configuración del usuario."""
        try:
            groq_client = self._get_groq_client(user_id, api_key)
            max_tokens = getattr(config, 'max_tokens', 1000)
            logger.info(f"🚀 Llamando a Groq API - Modelo: {model_name}, Temp: {config.temperature}")
            
            response = groq_client.chat.completions.create(
                messages=messages,
                model=model_name,
                temperature=config.temperature,
                max_tokens=max_tokens,
                stream=False
            )
            
            ai_response = response.choices[0].message.content
            usage_info = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "model": model_name,
                "temperature": config.temperature
            }
            logger.info(f"✅ Respuesta de Groq recibida - Tokens: {usage_info['total_tokens']}")
            return ai_response, usage_info
        
        except BadRequestError as e:
            error_msg = str(e)
            logger.error(f"❌ BadRequestError de Groq: {error_msg}")
            if "model" in error_msg.lower():
                raise ChatbotServiceError(
                    f"El modelo '{model_name}' no es válido para Groq. "
                    f"Modelos disponibles: llama-3.3-70b-versatile, llama-3.1-70b-versatile, "
                    f"llama-3.1-8b-instant, mixtral-8x7b-32768"
                )
            else:
                raise ChatbotServiceError(f"Error en la solicitud a Groq: {error_msg}")
        except APIError as e:
            error_msg = str(e)
            logger.error(f"❌ APIError de Groq: {error_msg}")
            if "403" in error_msg or "Forbidden" in error_msg:
                if user_id in self.groq_clients:
                    del self.groq_clients[user_id]
                    logger.info(f"🗑️ Cache de cliente Groq limpiado para usuario {user_id}")
                raise ChatbotServiceError(
                    "API key de Groq inválida o sin permisos. "
                    "Por favor, verifica tu API key en la configuración del chatbot. "
                    "Obtén una nueva en: https://console.groq.com/keys"
                )
            elif "429" in error_msg or "rate" in error_msg.lower():
                raise ChatbotServiceError(
                    "Has excedido el límite de solicitudes de Groq. "
                    "Por favor, intenta de nuevo en unos momentos."
                )
            else:
                raise ChatbotServiceError(f"Error de comunicación con Groq API: {error_msg}")
        except Exception as e:
            logger.error(f"❌ Error inesperado llamando a Groq API: {str(e)}")
            raise ChatbotServiceError(f"Error inesperado al comunicarse con Groq: {str(e)}")
    
    def _call_cerebras_api(
        self,
        user_id: int,
        api_key: str,
        messages: List[Dict[str, str]], 
        config: ChatbotConfig,
        model_name: str
    ) -> Tuple[str, Dict[str, Any]]:
        """Llama a la API de Cerebras usando la configuración del usuario."""
        try:
            cerebras_client = self._get_cerebras_client(user_id, api_key)
            max_tokens = getattr(config, 'max_tokens', 1000)
            logger.info(f"🚀 Llamando a Cerebras API - Modelo: {model_name}, Temp: {config.temperature}")
            
            response = cerebras_client.chat.completions.create(
                messages=messages,
                model=model_name,
                temperature=config.temperature,
                max_tokens=max_tokens,
                stream=False
            )
            
            ai_response = response.choices[0].message.content
            usage_info = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "model": model_name,
                "temperature": config.temperature
            }
            logger.info(f"✅ Respuesta de Cerebras recibida - Tokens: {usage_info['total_tokens']}")
            return ai_response, usage_info
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error llamando a Cerebras API: {error_msg}")
            
            # Detectar errores comunes de Cerebras
            if "401" in error_msg or "Unauthorized" in error_msg or "API key" in error_msg:
                if user_id in self.cerebras_clients:
                    del self.cerebras_clients[user_id]
                    logger.info(f"🗑️ Cache de cliente Cerebras limpiado para usuario {user_id}")
                raise ChatbotServiceError(
                    "API key de Cerebras inválida o sin permisos. "
                    "Por favor, verifica tu API key en la configuración del chatbot. "
                    "Obtén una nueva en: https://cloud.cerebras.ai/account/api-keys"
                )
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                raise ChatbotServiceError(
                    "Has excedido el límite de solicitudes de Cerebras. "
                    "Por favor, intenta de nuevo en unos momentos."
                )
            elif "model" in error_msg.lower() and "not found" in error_msg.lower():
                raise ChatbotServiceError(
                    f"El modelo '{model_name}' no es válido para Cerebras. "
                    f"Modelos disponibles: 'llama3.1-8b', 'llama-3.3-70b', 'gpt-oss-120b'"
                )
            else:
                raise ChatbotServiceError(f"Error al comunicarse con Cerebras: {error_msg}")


def get_chatbot_service(db_session: Session) -> ChatbotService:
    """Factory function para obtener una instancia del servicio."""
    return ChatbotService(db_session)