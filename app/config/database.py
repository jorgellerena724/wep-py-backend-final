from sqlmodel import SQLModel, create_engine, Session, text
from typing import Generator
from passlib.context import CryptContext
from app.config.config import settings 
import logging
import re

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conexión a la base de datos
try:
    # Aseguramos que la URL use 'postgresql://' en lugar de 'postgres://'
    database_url = settings.WEP_DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(database_url, echo=True)  # echo=True para ver queries en logs
except Exception as e:
    raise

# Verificar conexión a la base de datos
def verify_database_connection():
    """Verifica que la conexión a la base de datos funciona"""
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
            logger.info("✅ Conexión a la base de datos verificada correctamente")
        return True
    except Exception as e:
        logger.error(f"❌ Error al conectar a la base de datos: {e}")
        return False

# Contexto para hashing de contraseñas
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db() -> Generator:
    """Generador de sesiones de base de datos para esquema público"""
    with Session(engine) as session:
        yield session

def create_active_sessions_table():
    """Crea la tabla active_sessions si no existe"""
    try:
        with Session(engine) as session:
            session.exec(text("""
                CREATE TABLE IF NOT EXISTS public.active_sessions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    token TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP(6) NOT NULL,
                    last_action TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES public.user2(id) ON DELETE CASCADE
                )
            """))
            
            # Crear índices para optimizar consultas
            session.exec(text("""
                CREATE INDEX IF NOT EXISTS idx_active_sessions_user_id 
                ON public.active_sessions(user_id)
            """))
            
            session.exec(text("""
                CREATE INDEX IF NOT EXISTS idx_active_sessions_token 
                ON public.active_sessions(token)
            """))
            
            session.exec(text("""
                CREATE INDEX IF NOT EXISTS idx_active_sessions_expires_at 
                ON public.active_sessions(expires_at)
            """))
            
            session.commit()
    except Exception as e:
        logger.error(f"❌ Error al crear tabla active_sessions: {e}")
        raise

def create_admin_user():
    """Crea o verifica la existencia del usuario admin con client = 'shirkasoft'"""
    try:
        with Session(engine) as session:
            # Verificar si el usuario admin existe
            admin_email = "admin@shirkasoft.com"
            result = session.exec(
                text("SELECT COUNT(*) FROM public.user2 WHERE email = :email")
                .bindparams(email=admin_email)
            )
            count = result.scalar()
            
            if count == 0:
                # Hashear la contraseña
                plain_password = "maXS@sdasd1234"
                hashed_password = bcrypt_context.hash(plain_password)
                
                # Crear el usuario admin con client = 'shirkasoft'
                session.exec(
                    text("""
                        INSERT INTO public.user2 
                        (full_name, email, password, client) 
                        VALUES ('Super Admin', :email, :password, :client)
                    """).bindparams(
                        email=admin_email,
                        password=hashed_password,
                        client="shirkasoft"
                    )
                )
                session.commit()
                logger.info("✅ Usuario admin creado con client='shirkasoft'")
                
                # Crear esquema de shirkasoft automáticamente
                try:
                    create_tenant_schema("shirkasoft")
                except Exception as e:
                    logger.warning(f"⚠️ Error al crear esquema shirkasoft: {e}")
                    
            else:
                logger.info("Usuario admin ya existe")
                
                # Verificar si tiene el campo client, si no lo tiene, actualizarlo
                admin_result = session.exec(
                    text("SELECT client FROM public.user2 WHERE email = :email")
                    .bindparams(email=admin_email)
                )
                admin_client = admin_result.scalar()
                
                if not admin_client:
                    session.exec(
                        text("UPDATE public.user2 SET client = :client WHERE email = :email")
                        .bindparams(client="shirkasoft", email=admin_email)
                    )
                    session.commit()
                    logger.info("✅ Usuario admin actualizado con client='shirkasoft'")
                    
    except Exception as e:
        logger.error(f"❌ Error al crear/actualizar usuario admin: {e}")
        raise

def create_sqlmodel_tables():
    """Crea todas las tablas definidas con SQLModel"""
    try:
        # Asegurar que el esquema public existe
        with Session(engine) as session:
            session.exec(text("CREATE SCHEMA IF NOT EXISTS public;"))
            session.exec(text("SET search_path TO public;"))
            session.commit()
        
        # Crear todas las tablas de SQLModel
        SQLModel.metadata.create_all(engine)
        
        # Crear tabla active_sessions (no es SQLModel)
        create_active_sessions_table()
        
    except Exception as e:
        logger.error(f"❌ Error al crear tablas de SQLModel: {e}")
        raise

def create_public_initial_data():
    """Crea datos iniciales solo en el esquema público (para copiar estructura)"""
    logger.info("📊 Creando datos iniciales en esquema público...")
    
    try:
        with Session(engine) as session:
            # Estas funciones crean datos SOLO en public para que sirvan de plantilla
            create_initial_header()
            create_initial_contact()
            create_initial_company()
            create_initial_carrousels()
    except Exception as e:
        logger.error(f"❌ Error al crear datos iniciales públicos: {e}")
        raise

def init_database():
    """Inicializa la base de datos - función principal"""
    
    if not verify_database_connection():
        raise RuntimeError("No se pudo establecer conexión con la base de datos")
    
    try:
        create_sqlmodel_tables()          # 1. Crear tablas base
        create_admin_user()               # 2. Crear admin
        create_public_initial_data()      # 3. Crear datos iniciales
        verify_admin_user()               # 4. Verificar admin
        migrate_all_tenant_schemas()      # 5. Migrar tenants existentes (si hay)
        
    except Exception as e:
        logger.error(f"❌ Error crítico al inicializar base de datos: {e}")
        raise

def verify_admin_user():
    """Verifica si el usuario admin existe y muestra sus datos"""
    try:
        with Session(engine) as session:
            result = session.exec(
                text("""
                    SELECT id, full_name, email, client
                    FROM public.user2 
                    WHERE email = :email
                """).bindparams(email="admin@shirkasoft.com")
            )
            
            admin_user = result.first()
            
            if admin_user:
                logger.info(
                    f"✅ Usuario admin encontrado: "
                    f"ID={admin_user.id}, "
                    f"Nombre={admin_user.full_name}, "
                    f"Email={admin_user.email}, "
                    f"Client={admin_user.client}"
                )
                return True
            else:
                logger.warning("⚠️ Usuario admin no encontrado")
                return False
    except Exception as e:
        logger.error(f"❌ Error al verificar usuario admin: {e}")
        return False

# =============================================================================
# FUNCIONES PARA DATOS INICIALES EN PUBLIC (PLANTILLAS PARA TENANTS)
# =============================================================================

def create_initial_header():
    """Crea el registro inicial para el encabezado en public"""
    try:
        with Session(engine) as session:
            result = session.exec(text("SELECT COUNT(*) FROM public.header"))
            count = result.scalar()
            
            if count == 0:
                session.exec(
                    text("""
                        INSERT INTO public.header (name, logo)
                        VALUES (:name, :logo)
                    """).bindparams(name="Encabezado", logo=None)
                )
                session.commit()
            else:
                logger.info("  ⏭️ Header ya existe en public")
    except Exception as e:
        logger.error(f"  ❌ Error al crear header inicial: {e}")
        raise

def create_initial_contact():
    """Crea el registro inicial para el contacto en public"""
    try:
        with Session(engine) as session:
            result = session.exec(text("SELECT COUNT(*) FROM public.contact"))
            count = result.scalar()
            
            if count == 0:
                session.exec(
                    text("""
                        INSERT INTO public.contact (email, phone, address)
                        VALUES (:email, :phone, :address)
                    """).bindparams(
                        email="example@email.com",
                        phone="+7 234 1234",
                        address=None
                    )
                )
                session.commit()
            else:
                logger.info("  ⏭️ Contact ya existe en public")
    except Exception as e:
        logger.error(f"  ❌ Error al crear contacto inicial: {e}")
        raise

def create_initial_company():
    """Crea los registros iniciales para company en public"""
    company_data = [
        {'title': 'Título 1', 'description': 'Descripción para el título 1.', 'photo': None, 'status': True},
        {'title': 'Título 2', 'description': 'Descripción para el título 2.', 'photo': None, 'status': True},
        {'title': 'Título 3', 'description': 'Descripción para el título 3.', 'photo': None, 'status': True},
    ]
    
    try:
        with Session(engine) as session:
            result = session.exec(text("SELECT COUNT(*) FROM public.company"))
            count = result.scalar()
            
            if count == 0:
                for data in company_data:
                    session.exec(
                        text("""
                            INSERT INTO public.company (title, description, photo, status)
                            VALUES (:title, :description, :photo, :status)
                        """).bindparams(**data)
                    )
                session.commit()
            else:
                logger.info("  ⏭️ Companies ya existen en public")
    except Exception as e:
        logger.error(f"  ❌ Error al crear companies iniciales: {e}")
        raise

def create_initial_carrousels():
    """Crea registros iniciales para carrousel en public"""
    carrousel_data = [
        {"title": "Carrusel 1", "description": "Descripción del carrusel 1", 'photo': None, 'status': True},
        {"title": "Carrusel 2", "description": "Descripción del carrusel 2", 'photo': None, 'status': True},
        {"title": "Carrusel 3", "description": "Descripción del carrusel 3", 'photo': None, 'status': True},
        {"title": "Carrusel 4", "description": "Descripción del carrusel 4", 'photo': None, 'status': True},
        {"title": "Carrusel 5", "description": "Descripción del carrusel 5", 'photo': None, 'status': True},
    ]
    
    try:
        with Session(engine) as session:
            result = session.exec(text("SELECT COUNT(*) FROM public.carrousel"))
            count = result.scalar()
            
            if count == 0:
                for data in carrousel_data:
                    session.exec(
                        text("""
                            INSERT INTO public.carrousel (title, description, photo, status)
                            VALUES (:title, :description, :photo, :status)
                        """).bindparams(**data)
                    )
                session.commit()
            else:
                logger.info("  ⏭️ Carrousels ya existen en public")
    except Exception as e:
        logger.error(f"  ❌ Error al crear carrousels iniciales: {e}")
        raise

# =============================================================================
# FUNCIONES MULTITENANT
# =============================================================================

def validate_schema_name(schema_name: str) -> bool:
    """Valida que el nombre del esquema sea seguro (previene SQL injection)"""
    pattern = r'^[a-zA-Z0-9_]{1,50}$'
    return bool(re.match(pattern, schema_name))

def get_all_tables_except_user():
    """Obtiene todas las tablas del esquema public excepto user2 y active_sessions"""
    try:
        with Session(engine) as session:
            result = session.exec(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                AND table_name NOT IN ('user2', 'active_sessions', 'google_calendar_tokens')
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]
            return tables
    except Exception as e:
        logger.error(f"Error al obtener lista de tablas: {e}")
        return []

def create_tenant_schema(client_name: str):
    """Crea un esquema para un nuevo tenant y copia TODAS las tablas necesarias"""
    if not validate_schema_name(client_name):
        raise ValueError(f"Nombre de esquema inválido: {client_name}")
    
    try:
        with Session(engine) as session:
            # Verificar si el esquema ya existe
            schema_exists = session.exec(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.schemata 
                    WHERE schema_name = :schema_name
                )
            """).bindparams(schema_name=client_name)).scalar()
            
            if schema_exists:
                migrate_existing_tenant_schema(client_name)
                return
            
            # 1. Crear el esquema
            session.exec(text(f"CREATE SCHEMA IF NOT EXISTS {client_name}"))
            
            # 2. Obtener todas las tablas del esquema public (excepto user2 y active_sessions)
            tables_to_create = get_all_tables_except_user()
            
            if not tables_to_create:
                logger.warning("⚠️ No se encontraron tablas para copiar")
                return
            
            # 3. Crear todas las tablas en el esquema del cliente
            for table_name in tables_to_create:
                try:
                    session.exec(text(f"""
                        CREATE TABLE IF NOT EXISTS {client_name}.{table_name} 
                        (LIKE public.{table_name} INCLUDING ALL)
                    """))
                    logger.info(f"  ✅ Tabla '{table_name}' creada en esquema '{client_name}'")
                except Exception as table_error:
                    logger.error(f"  ❌ Error al crear tabla '{table_name}': {table_error}")
                    continue
            
            session.commit()
            
            # 4. Crear datos iniciales solo para las tablas específicas
            create_tenant_initial_data(client_name)
            
    except Exception as e:
        logger.error(f"❌ Error al crear esquema para tenant '{client_name}': {e}")
        raise

def create_tenant_initial_data(client_name: str):
    """Copia TODOS los datos iniciales desde public a tenant automáticamente"""
    if not validate_schema_name(client_name):
        raise ValueError(f"Nombre de esquema inválido: {client_name}")
        
    try:
        with Session(engine) as session:
            logger.info(f"📊 Copiando todos los datos iniciales para tenant '{client_name}'...")
            
            # Lista específica de tablas que deben tener datos iniciales
            tables_with_initial_data = ['header', 'contact', 'company', 'carrousel']
            
            # Verificar que las tablas existen en ambos esquemas
            for table_name in tables_with_initial_data:
                try:
                    # Verificar si la tabla existe en public y tiene datos
                    public_count_result = session.exec(text(f"SELECT COUNT(*) FROM public.{table_name}"))
                    public_count = public_count_result.scalar()
                    
                    if public_count == 0:
                        logger.warning(f"  ⚠️ Tabla 'public.{table_name}' vacía, creando datos iniciales...")
                        # Si no hay datos en public, crearlos primero
                        if table_name == 'header':
                            create_initial_header()
                        elif table_name == 'contact':
                            create_initial_contact()
                        elif table_name == 'company':
                            create_initial_company()
                        elif table_name == 'carrousel':
                            create_initial_carrousels()
                        
                        # Volver a contar después de crear
                        public_count_result = session.exec(text(f"SELECT COUNT(*) FROM public.{table_name}"))
                        public_count = public_count_result.scalar()
                    
                    # Verificar si la tabla en tenant existe
                    tenant_table_exists = session.exec(text("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = :schema_name 
                            AND table_name = :table_name
                        )
                    """).bindparams(schema_name=client_name, table_name=table_name)).scalar()
                    
                    if not tenant_table_exists:
                        logger.warning(f"  ⚠️ Tabla '{client_name}.{table_name}' no existe, creándola...")
                        session.exec(text(f"""
                            CREATE TABLE IF NOT EXISTS {client_name}.{table_name} 
                            (LIKE public.{table_name} INCLUDING ALL)
                        """))
                        session.commit()
                    
                    # Verificar si la tabla en tenant ya tiene datos
                    tenant_count_result = session.exec(text(f"SELECT COUNT(*) FROM {client_name}.{table_name}"))
                    tenant_count = tenant_count_result.scalar()
                    
                    if tenant_count > 0:
                        continue
                    
                    # Copiar todos los datos desde public a tenant
                    if public_count > 0:
                        session.exec(text(f"""
                            INSERT INTO {client_name}.{table_name} 
                            SELECT * FROM public.{table_name}
                        """))
                        logger.info(f"  ✅ {public_count} registros copiados de '{table_name}' a '{client_name}'")
                    else:
                        logger.warning(f"  ⚠️ No hay datos que copiar de 'public.{table_name}'")
                    
                except Exception as e:
                    logger.error(f"  ❌ Error al copiar datos de '{table_name}': {e}")
                    continue
            
            session.commit()
            
    except Exception as e:
        logger.error(f"❌ Error al copiar datos iniciales para tenant '{client_name}': {e}")
        raise

def get_tenant_db(client_name: str) -> Generator:
    if not validate_schema_name(client_name):
        raise ValueError(f"Nombre de esquema inválido: {client_name}")
    
    with Session(engine) as session:
        try:
            # Configurar búsqueda en el esquema del cliente + public
            session.exec(text(f"SET search_path TO {client_name}, public"))
            yield session
        finally:
            # Restaurar configuración original
            session.exec(text("SET search_path TO public"))

def migrate_existing_tenant_schema(client_name: str):
    """Migra un esquema de tenant existente agregando tablas faltantes"""
    if not validate_schema_name(client_name):
        raise ValueError(f"Nombre de esquema inválido: {client_name}")
    
    try:
        with Session(engine) as session:
            # Verificar que el esquema existe
            schema_exists = session.exec(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.schemata 
                    WHERE schema_name = :schema_name
                )
            """).bindparams(schema_name=client_name)).scalar()
            
            if not schema_exists:
                create_tenant_schema(client_name)
                return
            
            # Obtener tablas disponibles y existentes
            public_tables = get_all_tables_except_user()
            existing_tenant_tables = session.exec(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = :schema_name 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """).bindparams(schema_name=client_name))
            
            existing_tables = [row[0] for row in existing_tenant_tables.fetchall()]
            missing_tables = [table for table in public_tables if table not in existing_tables]
            
            if not missing_tables:
                # Aún así, verificar que tienen datos iniciales
                create_tenant_initial_data(client_name)
                return
            
            # Crear tablas faltantes
            for table_name in missing_tables:
                try:
                    session.exec(text(f"""
                        CREATE TABLE IF NOT EXISTS {client_name}.{table_name} 
                        (LIKE public.{table_name} INCLUDING ALL)
                    """))
                except Exception as table_error:
                    logger.error(f"  ❌ Error al crear tabla '{table_name}': {table_error}")
                    continue
            
            session.commit()
            
            # Copiar datos iniciales para las nuevas tablas
            create_tenant_initial_data(client_name)
            
    except Exception as e:
        logger.error(f"❌ Error al migrar esquema '{client_name}': {e}")
        raise

def migrate_all_tenant_schemas():
    """Migra todos los esquemas de tenant existentes"""
    try:
        with Session(engine) as session:
            clients = session.exec(text("""
                SELECT DISTINCT client 
                FROM public.user2 
                WHERE client IS NOT NULL 
                AND client != ''
                ORDER BY client
            """))
            
            client_list = [row[0] for row in clients.fetchall()]
            
            if not client_list:
                return
            
            for client_name in client_list:
                try:
                    migrate_existing_tenant_schema(client_name)
                except Exception as e:
                    logger.error(f"❌ Error al migrar tenant '{client_name}': {e}")
                    continue
            
    except Exception as e:
        logger.error(f"❌ Error en migración masiva: {e}")
        raise

# =============================================================================
# FUNCIÓN PRINCIPAL PARA CREAR TENANT CUANDO SE REGISTRA UN NUEVO USUARIO
# =============================================================================

def setup_new_tenant(client_name: str):
    """
    Función principal para configurar un nuevo tenant cuando se crea un usuario.
    Esta función debe ser llamada desde el endpoint de registro de usuarios.
    """
    if not client_name or client_name.strip() == "":
        return False
        
    client_name = client_name.strip().lower()
    
    try:
        
        # Verificar si el esquema ya existe
        with Session(engine) as session:
            schema_exists = session.exec(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.schemata 
                    WHERE schema_name = :schema_name
                )
            """).bindparams(schema_name=client_name)).scalar()
            
            if schema_exists:
                migrate_existing_tenant_schema(client_name)
            else:
                create_tenant_schema(client_name)
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al configurar tenant '{client_name}': {e}")
        return False