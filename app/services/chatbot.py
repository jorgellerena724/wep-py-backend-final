from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Tuple, Any
from sqlmodel import Session, func, select
from sqlalchemy.orm import selectinload
from groq import Groq, BadRequestError, APIError, APIStatusError
from groq import AuthenticationError, PermissionDeniedError, NotFoundError, RateLimitError, APIConnectionError

from app.models.wep_chatbot_model import ChatbotConfig, ChatbotModel, ChatbotUsage
from app.config.config import settings

logger = logging.getLogger(__name__)


class ChatbotServiceError(Exception):
    """Excepción personalizada para errores del servicio de chatbot"""
    pass


class ChatbotService:
    """
    Servicio simplificado para manejar el chatbot.
    Solo procesa mensajes usando configuración de BD.
    No gestiona sesiones - eso lo hace el frontend.
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.groq_clients = {}  # Cache de clientes Groq por usuario
        logger.info("✅ ChatbotService inicializado")
    
    def _get_groq_client(self, user_id: int, api_key: str) -> Groq:
        """
        Obtiene o crea un cliente de Groq para un usuario específico.
        """
        try:
            # Buscar en cache
            if user_id in self.groq_clients:
                return self.groq_clients[user_id]
            
            if not api_key:
                raise ChatbotServiceError("API key de Groq no configurada")
            
            # Crear cliente de Groq
            groq_client = Groq(api_key=api_key)
            
            # Guardar en cache
            self.groq_clients[user_id] = groq_client
            
            logger.info(f"✅ Cliente Groq creado para usuario {user_id}")
            return groq_client
            
        except Exception as e:
            logger.error(f"❌ Error creando cliente Groq: {str(e)}")
            raise ChatbotServiceError(f"No se pudo inicializar el cliente Groq: {str(e)}")
    
    def _get_user_config(self, user_id: int) -> Optional[ChatbotConfig]:
        """
        Obtiene la configuración del chatbot para un usuario desde la BD.
        Usa selectinload para cargar el modelo relacionado.
        """
        try:
            logger.info(f"🔍 Buscando configuración para user_id: {user_id}")
            
            # Asegurarse de que user_id es un entero
            if not isinstance(user_id, int):
                try:
                    user_id = int(user_id)
                except (ValueError, TypeError):
                    logger.error(f"❌ user_id inválido: {user_id}")
                    return None
            
            config = self.db.exec(
                select(ChatbotConfig)
                .options(selectinload(ChatbotConfig.model))
                .where(ChatbotConfig.user_id == user_id)
            ).first()
            
            if config:
                logger.info(f"✅ Configuración encontrada - Modelo: {config.model.name if config.model else 'N/A'}")
            else:
                logger.warning(f"⚠️ No se encontró configuración para user_id: {user_id}")
            
            return config
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo configuración: {str(e)}")
            return None
    
    def process_message(
        self,
        user_id: int,
        user_message: str,
        session_key: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[str, Dict[str, Any], str]:
        """
        Procesa un mensaje del usuario y devuelve la respuesta del chatbot.
        
        Args:
            user_id: ID del usuario (entero, obtenido del token o del owner)
            user_message: Mensaje del usuario
            session_key: Clave de sesión (generada y manejada por el frontend)
            conversation_history: Historial de conversación enviado por el frontend (opcional)
        
        Returns:
            tuple: (respuesta_ai, metadatos, session_key)
        """
        logger.info(f"💬 Procesando mensaje para user_id: {user_id}")
        
        try:
            # 1. Validar mensaje
            if not user_message or len(user_message.strip()) == 0:
                raise ChatbotServiceError("El mensaje no puede estar vacío")
            
            max_length = getattr(settings, 'MAX_MESSAGE_LENGTH', 2000)
            if len(user_message) > max_length:
                user_message = user_message[:max_length]
                logger.warning(f"⚠️ Mensaje truncado a {max_length} caracteres")
            
            # 2. Generar o mantener session_key (manejado por frontend)
            if not session_key:
                import uuid
                session_key = f"session_{user_id}_{uuid.uuid4().hex[:8]}"
                logger.info(f"🆕 Nueva sesión: {session_key}")
            
            # 3. Obtener configuración del usuario (incluye modelo con selectinload)
            config = self._get_user_config(user_id)
            
            if not config:
                raise ChatbotServiceError(
                    "No se encontró configuración de chatbot. "
                    "Por favor, configura el chatbot desde el dashboard."
                )
            
            if not config.status:
                raise ChatbotServiceError("El chatbot está desactivado")
            
            # 4. Verificar que el modelo está cargado
            if not config.model:
                raise ChatbotServiceError("Modelo de IA no encontrado en la configuración")
            
            model_name = config.model.name
            logger.info(f"🤖 Usando modelo: {model_name}")
            
            today_date = datetime.now(timezone.utc).date()
            today_datetime = datetime.combine(today_date, datetime.min.time())
            
            usage_record = self.db.exec(
                select(ChatbotUsage).where(
                    ChatbotUsage.api_key == config.api_key,
                    ChatbotUsage.model_id == config.model_id,
                    func.date(ChatbotUsage.date) == today_date
                )
            ).first()
            
            if not usage_record:
                usage_record = ChatbotUsage(
                    user_id=user_id,
                    api_key=config.api_key,
                    model_id=config.model.id,
                    date=today_datetime,
                    tokens_used=0
                )
                self.db.add(usage_record)
                self.db.commit()
                self.db.refresh(usage_record)

            # Cargamos el modelo para ver su límite
            model_limit = config.model.daily_token_limit
            
            if usage_record.tokens_used >= model_limit:
                raise ChatbotServiceError(f"Límite diario excedido para el modelo {config.model.name}")
            
            # 5. Construir mensajes para Groq
            messages = self._build_groq_messages(
                config=config,
                user_message=user_message,
                conversation_history=conversation_history
            )
            
            # 6. Llamar a Groq API
            ai_response, usage_info = self._call_groq_api(
                user_id=user_id,
                api_key=config.api_key,
                messages=messages,
                config=config,
                model_name=model_name
            )
            
            usage_record.tokens_used += usage_info.get('total_tokens', 0)
            usage_record.date = today_datetime
            self.db.add(usage_record)
            self.db.commit()
            
            logger.info(
                f"✅ Mensaje procesado - Usuario: {user_id}, "
                f"Tokens: {usage_info.get('total_tokens', 0)}"
            )
            
            return ai_response, usage_info, session_key
            
        except ChatbotServiceError:
            raise
        except Exception as e:
            logger.error(f"❌ Error inesperado: {str(e)}", exc_info=True)
            raise ChatbotServiceError(f"Error interno del servidor: {str(e)}")
    
    def _build_groq_messages(
        self,
        config: ChatbotConfig,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, str]]:
        """
        Construye la lista de mensajes para enviar a Groq API.
        El historial viene del frontend si lo envía.
        """
        messages = []
        
        # 1. Prompt del sistema (desde BD)
        messages.append({
            "role": "system",
            "content": config.prompt
        })
        
        # 2. Historial de conversación (si el frontend lo envía)
        if conversation_history:
            messages.extend(conversation_history)
        
        # 3. Mensaje actual del usuario
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        logger.info(f"📝 Construidos {len(messages)} mensajes para Groq")
        
        return messages
    
    def _call_groq_api(
        self,
        user_id: int,
        api_key: str,
        messages: List[Dict[str, str]], 
        config: ChatbotConfig,
        model_name: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Llama a la API de Groq usando la configuración del usuario.
        """
        try:
            # Obtener cliente de Groq
            groq_client = self._get_groq_client(user_id, api_key)
            
            # Preparar parámetros
            max_tokens = getattr(config, 'max_tokens', 1000)
            
            api_key_preview = f"{api_key[:8]}..." if api_key else "VACÍA"
            logger.info("=" * 60)
            logger.info(f"🚀 GROQ REQUEST - User: {user_id}")
            logger.info(f"   Modelo: {model_name}")
            logger.info(f"   API Key: {api_key_preview}")
            logger.info(f"   Temp: {config.temperature}, Max Tokens: {max_tokens}")
            logger.info(f"   Mensajes: {len(messages)}")
            logger.info(f"   Prompt sistema: {config.prompt[:100] if config.prompt else 'N/A'}...")
            logger.info("=" * 60)
            
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
            
            logger.info(f"✅ GROQ RESPONSE OK - Tokens: {usage_info['total_tokens']} "
                        f"(prompt: {usage_info['prompt_tokens']}, completion: {usage_info['completion_tokens']})")
            logger.info(f"   Respuesta (primeros 200): {ai_response[:200] if ai_response else 'VACÍA'}...")
            
            return ai_response, usage_info
            
        except AuthenticationError as e:
            status = getattr(e, 'status_code', '?')
            body = getattr(e, 'body', '?')
            logger.error(f"❌ GROQ AuthenticationError (HTTP {status})")
            logger.error(f"   Body: {body}")
            logger.error(f"   Message: {e}")
            if user_id in self.groq_clients:
                del self.groq_clients[user_id]
                logger.info(f"🗑️ Cache limpiado para usuario {user_id}")
            raise ChatbotServiceError(
                "API key de Groq inválida (HTTP 401). "
                "La key no existe o fue revocada. "
                "Verifica en: https://console.groq.com/keys"
            )
            
        except PermissionDeniedError as e:
            status = getattr(e, 'status_code', '?')
            body = getattr(e, 'body', '?')
            logger.error(f"❌ GROQ PermissionDeniedError (HTTP {status})")
            logger.error(f"   Body: {body}")
            logger.error(f"   Message: {e}")
            if user_id in self.groq_clients:
                del self.groq_clients[user_id]
                logger.info(f"🗑️ Cache limpiado para usuario {user_id}")
            raise ChatbotServiceError(
                f"API key de Groq sin permisos para el modelo '{model_name}' (HTTP 403). "
                "Verifica que tu plan de Groq incluya este modelo."
            )
            
        except NotFoundError as e:
            status = getattr(e, 'status_code', '?')
            body = getattr(e, 'body', '?')
            logger.error(f"❌ GROQ NotFoundError (HTTP {status})")
            logger.error(f"   Body: {body}")
            logger.error(f"   Message: {e}")
            raise ChatbotServiceError(
                f"El modelo '{model_name}' no existe en Groq. "
                f"Verifica el nombre del modelo en la configuración."
            )
            
        except RateLimitError as e:
            status = getattr(e, 'status_code', '?')
            body = getattr(e, 'body', '?')
            logger.error(f"❌ GROQ RateLimitError (HTTP {status})")
            logger.error(f"   Body: {body}")
            logger.error(f"   Message: {e}")
            raise ChatbotServiceError(
                "Límite de solicitudes de Groq excedido. "
                "Espera unos momentos e intenta de nuevo."
            )
            
        except APIConnectionError as e:
            logger.error(f"❌ GROQ APIConnectionError - No se pudo conectar a Groq")
            logger.error(f"   Message: {e}")
            raise ChatbotServiceError(
                "No se pudo conectar con Groq. "
                "Verifica la conexión a internet."
            )
            
        except BadRequestError as e:
            error_msg = str(e)
            status = getattr(e, 'status_code', '?')
            body = getattr(e, 'body', '?')
            logger.error(f"❌ GROQ BadRequestError (HTTP {status})")
            logger.error(f"   Body: {body}")
            logger.error(f"   Message: {error_msg}")
            
            if "model" in error_msg.lower():
                raise ChatbotServiceError(
                    f"El modelo '{model_name}' no es válido. "
                    f"Modelos disponibles: llama-3.3-70b-versatile, llama-3.1-70b-versatile, "
                    f"llama-3.1-8b-instant, mixtral-8x7b-32768"
                )
            else:
                raise ChatbotServiceError(f"Error en la solicitud a Groq: {error_msg}")
                
        except APIStatusError as e:
            status = getattr(e, 'status_code', '?')
            body = getattr(e, 'body', '?')
            logger.error(f"❌ GROQ APIStatusError (HTTP {status})")
            logger.error(f"   Body: {body}")
            logger.error(f"   Message: {e}")
            raise ChatbotServiceError(
                f"Error HTTP {status} de Groq. "
                "Revisa los logs para más detalles."
            )
                
        except APIError as e:
            error_msg = str(e)
            logger.error(f"❌ GROQ APIError (genérico): {error_msg}")
            raise ChatbotServiceError(f"Error de comunicación con Groq API: {error_msg}")
                
        except Exception as e:
            logger.error(f"❌ GROQ Error inesperado: {str(e)}", exc_info=True)
            raise ChatbotServiceError(f"Error inesperado al comunicarse con Groq: {str(e)}")


def get_chatbot_service(db_session: Session) -> ChatbotService:
    """Factory function para obtener una instancia del servicio."""
    return ChatbotService(db_session)