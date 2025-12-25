"""
Script para inicializar las tablas del chatbot en cada esquema.
Se ejecuta una vez por cliente al activar el chatbot.
"""
import logging
from sqlmodel import Session, text
from app.models.chatbot_models import ChatbotConfig
from app.config.database import engine

logger = logging.getLogger(__name__)

def create_chatbot_tables_for_tenant(tenant_schema: str):
    """
    Crea las tablas del chatbot en el esquema de un tenant específico.
    
    Args:
        tenant_schema: Nombre del esquema (ej: 'cliente_001')
    """
    
    # SQL para crear las tablas en PostgreSQL
    create_tables_sql = [
        # Tabla chatbot_config
        f"""
        CREATE TABLE IF NOT EXISTS {tenant_schema}.chatbot_config (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(255) NOT NULL,
            groq_model VARCHAR(100) DEFAULT 'llama-3.3-70b-versatile',
            system_prompt TEXT DEFAULT 'Eres un asistente virtual útil y amable. Responde en español de manera profesional.',
            temperature FLOAT DEFAULT 0.7,
            max_tokens INTEGER DEFAULT 500,
            max_history INTEGER DEFAULT 10,
            session_ttl_minutes INTEGER DEFAULT 30,
            enable_history BOOLEAN DEFAULT TRUE,
            company_name VARCHAR(255),
            company_description TEXT,
            contact_info TEXT,
            branding TEXT,
            welcome_message TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_chatbot_config_tenant 
        ON {tenant_schema}.chatbot_config(tenant_id);
        """,
        
        # Tabla chat_sessions
        f"""
        CREATE TABLE IF NOT EXISTS {tenant_schema}.chat_sessions (
            id SERIAL PRIMARY KEY,
            session_key VARCHAR(100) UNIQUE NOT NULL,
            tenant_id VARCHAR(255) NOT NULL,
            user_identifier VARCHAR(255),
            user_ip VARCHAR(45),
            user_agent TEXT,
            page_url TEXT,
            message_count INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            metadata TEXT
        );
        
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_key 
        ON {tenant_schema}.chat_sessions(session_key);
        
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_tenant 
        ON {tenant_schema}.chat_sessions(tenant_id);
        
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_expires 
        ON {tenant_schema}.chat_sessions(expires_at) WHERE is_active = TRUE;
        """,
        
        # Tabla chat_messages
        f"""
        CREATE TABLE IF NOT EXISTS {tenant_schema}.chat_messages (
            id SERIAL PRIMARY KEY,
            session_key VARCHAR(100) NOT NULL,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            tokens INTEGER,
            model_used VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            message_order INTEGER DEFAULT 0,
            FOREIGN KEY (session_key) 
            REFERENCES {tenant_schema}.chat_sessions(session_key) 
            ON DELETE CASCADE
        );
        
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session 
        ON {tenant_schema}.chat_messages(session_key);
        
        CREATE INDEX IF NOT EXISTS idx_chat_messages_created 
        ON {tenant_schema}.chat_messages(created_at);
        """,
        
        # Tabla chatbot_usage_stats (opcional)
        f"""
        CREATE TABLE IF NOT EXISTS {tenant_schema}.chatbot_usage_stats (
            id SERIAL PRIMARY KEY,
            tenant_id VARCHAR(255) NOT NULL,
            date VARCHAR(10) NOT NULL,
            total_sessions INTEGER DEFAULT 0,
            active_sessions INTEGER DEFAULT 0,
            total_messages INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            estimated_cost FLOAT DEFAULT 0.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, date)
        );
        
        CREATE INDEX IF NOT EXISTS idx_usage_stats_tenant_date 
        ON {tenant_schema}.chatbot_usage_stats(tenant_id, date);
        """
    ]
    
    try:
        with Session(engine) as session:
            # 1. Verificar que el esquema existe
            session.exec(text(f"SET search_path TO {tenant_schema}, public"))
            
            # 2. Crear tablas
            for sql in create_tables_sql:
                session.exec(text(sql))
            
            session.commit()
            
            # 3. Crear configuración por defecto si no existe
            existing_config = session.exec(
                text(f"SELECT 1 FROM {tenant_schema}.chatbot_config WHERE tenant_id = :tenant_id")
            ).params(tenant_id=tenant_schema).first()
            
            if not existing_config:
                insert_sql = f"""
                INSERT INTO {tenant_schema}.chatbot_config (tenant_id, company_name, welcome_message)
                VALUES (:tenant_id, :company_name, :welcome_message)
                """
                session.exec(
                    text(insert_sql).params(
                        tenant_id=tenant_schema,
                        company_name=tenant_schema.replace('_', ' ').title(),
                        welcome_message=f"¡Hola! Soy el asistente virtual de {tenant_schema.replace('_', ' ').title()}. ¿En qué puedo ayudarte?"
                    )
                )
                session.commit()
            
            logger.info(f"✅ Tablas del chatbot creadas para tenant: {tenant_schema}")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error creando tablas para {tenant_schema}: {str(e)}")
        return False


def initialize_chatbot_for_all_tenants():
    """
    Inicializa el chatbot para todos los clientes existentes.
    Se ejecuta al iniciar la aplicación o manualmente.
    """
    logger.info("🚀 Inicializando chatbot para todos los tenants...")
    
    try:
        with Session(engine) as session:
            # Obtener todos los esquemas existentes
            # Ajusta esta consulta según cómo manejas los esquemas
            schemas = session.exec(
                text("""
                    SELECT schema_name 
                    FROM information_schema.schemata 
                    WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'public')
                    AND schema_name NOT LIKE 'pg_%'
                """)
            ).all()
            
            logger.info(f"📋 Esquemas encontrados: {len(schemas)}")
            
            for schema in schemas:
                schema_name = schema[0]
                logger.info(f"  • Procesando: {schema_name}")
                create_chatbot_tables_for_tenant(schema_name)
            
            logger.info("✅ Inicialización completada")
            return len(schemas)
            
    except Exception as e:
        logger.error(f"❌ Error en inicialización: {str(e)}")
        return 0