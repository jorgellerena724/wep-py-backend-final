import json
from sqlmodel import SQLModel, create_engine, Session, text
from typing import Generator
from passlib.context import CryptContext
from app.config.config import settings 
import logging
import re


DEFAULT_SOCIAL_NETWORKS = [
    {"network": "whatsapp", "url": "https://wa.me/", "username": "", "active": False},
    {"network": "facebook", "url": "https://facebook.com/", "username": "", "active": False},
    {"network": "instagram", "url": "https://instagram.com/", "username": "", "active": False},
    {"network": "tiktok", "url": "https://tiktok.com/@", "username": "", "active": False},
    {"network": "x", "url": "https://x.com/", "username": "", "active": False},
    {"network": "telegram", "url": "https://t.me/", "username": "", "active": False},
]

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Determinar la URL de base de datos
database_url = settings.get_database_url()
is_sqlite = settings.USE_SQLITE

# Configurar el motor de base de datos
try:
    if is_sqlite:
        # SQLite configuration
        engine = create_engine(
            database_url, 
            echo=True,
            connect_args={"check_same_thread": False}  # Necesario para SQLite
        )
        logger.info("✅ Usando SQLite como base de datos")
    else:
        # PostgreSQL configuration
        engine = create_engine(database_url, echo=True)
        logger.info("✅ Usando PostgreSQL como base de datos")
except Exception as e:
    logger.error(f"❌ Error al crear el motor de base de datos: {e}")
    raise

# Contexto para hashing de contraseñas
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db() -> Generator:
    """Generador de sesiones de base de datos"""
    with Session(engine) as session:
        yield session

def is_postgresql() -> bool:
    """Verifica si estamos usando PostgreSQL"""
    return not is_sqlite

def is_sqlite_db() -> bool:
    """Verifica si estamos usando SQLite"""
    return is_sqlite

def get_schema_prefix(schema_name: str) -> str:
    """Retorna el prefijo de esquema según la base de datos"""
    if is_sqlite:
        return ""  # SQLite no usa esquemas
    else:
        return f"{schema_name}." if schema_name != 'public' else ""

def verify_database_connection():
    """Verifica que la conexión a la base de datos funciona"""
    try:
        with Session(engine) as session:
            if is_sqlite:
                session.exec(text("SELECT 1"))
            else:
                session.exec(text("SELECT 1"))
            logger.info("✅ Conexión a la base de datos verificada correctamente")
        return True
    except Exception as e:
        logger.error(f"❌ Error al conectar a la base de datos: {e}")
        return False

def create_active_sessions_table():
    """Crea la tabla active_sessions si no existe"""
    try:
        with Session(engine) as session:
            if is_sqlite:
                # SQLite version
                session.exec(text("""
                    CREATE TABLE IF NOT EXISTS active_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        token TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL,
                        last_action TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES user2(id) ON DELETE CASCADE
                    )
                """))
                
                # Crear índices para SQLite
                session.exec(text("""
                    CREATE INDEX IF NOT EXISTS idx_active_sessions_user_id 
                    ON active_sessions(user_id)
                """))
                
                session.exec(text("""
                    CREATE INDEX IF NOT EXISTS idx_active_sessions_token 
                    ON active_sessions(token)
                """))
                
                session.exec(text("""
                    CREATE INDEX IF NOT EXISTS idx_active_sessions_expires_at 
                    ON active_sessions(expires_at)
                """))
            else:
                # PostgreSQL version
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
                
                # Crear índices para PostgreSQL
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
            
            if is_sqlite:
                result = session.exec(
                    text("SELECT COUNT(*) FROM user2 WHERE email = :email")
                    .bindparams(email=admin_email)
                )
            else:
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
                if is_sqlite:
                    session.exec(
                        text("""
                            INSERT INTO user2 
                            (full_name, email, password, client) 
                            VALUES ('Super Admin', :email, :password, :client)
                        """).bindparams(
                            email=admin_email,
                            password=hashed_password,
                            client="shirkasoft"
                        )
                    )
                else:
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
                
                # Para SQLite, no creamos esquemas
                if not is_sqlite:
                    try:
                        create_tenant_schema("shirkasoft")
                    except Exception as e:
                        logger.warning(f"⚠️ Error al crear esquema shirkasoft: {e}")
                    
            else:
                logger.info("Usuario admin ya existe")
                
                # Verificar si tiene el campo client, si no lo tiene, actualizarlo
                if is_sqlite:
                    admin_result = session.exec(
                        text("SELECT client FROM user2 WHERE email = :email")
                        .bindparams(email=admin_email)
                    )
                else:
                    admin_result = session.exec(
                        text("SELECT client FROM public.user2 WHERE email = :email")
                        .bindparams(email=admin_email)
                    )
                
                admin_client = admin_result.scalar()
                
                if not admin_client:
                    if is_sqlite:
                        session.exec(
                            text("UPDATE user2 SET client = :client WHERE email = :email")
                            .bindparams(client="shirkasoft", email=admin_email)
                        )
                    else:
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
        # Para PostgreSQL, asegurar que el esquema public existe
        if not is_sqlite:
            with Session(engine) as session:
                session.exec(text("CREATE SCHEMA IF NOT EXISTS public;"))
                session.exec(text("SET search_path TO public;"))
                session.commit()
        
        # Crear todas las tablas de SQLModel
        # Ahora todos los modelos están registrados en SQLModel.metadata
        logger.info(f"📋 Creando tablas de SQLModel. Total de tablas: {len(SQLModel.metadata.tables)}")
        SQLModel.metadata.create_all(engine)
        logger.info("✅ Tablas de SQLModel creadas correctamente")
        
        # Crear tabla active_sessions (no es SQLModel)
        create_active_sessions_table()
        
    except Exception as e:
        logger.error(f"❌ Error al crear tablas de SQLModel: {e}")
        raise

def create_public_initial_data():
    """Crea datos iniciales solo en el esquema público (para copiar estructura)"""
    logger.info("📊 Creando datos iniciales...")
    
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

def migrate_news_fecha_column():
    """Migra la columna fecha en la tabla news para permitir NULL"""
    try:
        with Session(engine) as session:
            # Verificar si la tabla news existe
            if is_sqlite:
                table_exists_result = session.exec(text("""
                    SELECT COUNT(*) FROM sqlite_master 
                    WHERE type='table' AND name='news'
                """))
                table_count = table_exists_result.scalar()
                if table_count == 0:
                    logger.info("⏭️ Tabla news no existe aún, se creará con la estructura correcta")
                    return
                
                # SQLite no soporta ALTER COLUMN directamente, necesitamos recrear la tabla
                # Verificar si la columna fecha existe y tiene restricción NOT NULL
                result = session.exec(text("""
                    SELECT sql FROM sqlite_master 
                    WHERE type='table' AND name='news'
                """))
                table_sql = result.scalar()
                
                if table_sql and 'fecha' in table_sql:
                    # Verificar si necesita migración (buscar 'fecha' seguido de NOT NULL)
                    # Patrón: fecha DATE NOT NULL o fecha NOT NULL
                    fecha_pattern = r'fecha\s+\w*\s*NOT\s+NULL'
                    needs_migration = re.search(fecha_pattern, table_sql, re.IGNORECASE) is not None
                    
                    if needs_migration:
                        logger.info("🔧 Migrando columna fecha en tabla news (SQLite)...")
                        
                        # Crear tabla temporal con la nueva estructura
                        session.exec(text("""
                            CREATE TABLE news_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                title VARCHAR(100) NOT NULL,
                                description TEXT NOT NULL,
                                fecha DATE,
                                photo VARCHAR(80) NOT NULL,
                                status BOOLEAN NOT NULL DEFAULT 1
                            )
                        """))
                        
                        # Copiar datos de la tabla antigua a la nueva
                        session.exec(text("""
                            INSERT INTO news_new (id, title, description, fecha, photo, status)
                            SELECT id, title, description, fecha, photo, status
                            FROM news
                        """))
                        
                        # Eliminar tabla antigua
                        session.exec(text("DROP TABLE news"))
                        
                        # Renombrar tabla nueva
                        session.exec(text("ALTER TABLE news_new RENAME TO news"))
                        
                        session.commit()
                        logger.info("✅ Migración de columna fecha completada (SQLite)")
                    else:
                        logger.info("⏭️ Columna fecha ya permite NULL (SQLite)")
            else:
                # PostgreSQL: usar ALTER TABLE directamente
                # Verificar si la tabla existe
                table_exists = session.exec(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'news'
                    )
                """))
                
                if not table_exists.scalar():
                    logger.info("⏭️ Tabla news no existe aún, se creará con la estructura correcta")
                    return
                
                # Verificar si la columna permite NULL
                result = session.exec(text("""
                    SELECT is_nullable 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'news' 
                    AND column_name = 'fecha'
                """))
                
                is_nullable = result.scalar()
                
                if is_nullable == 'NO':
                    logger.info("🔧 Migrando columna fecha en tabla news (PostgreSQL)...")
                    session.exec(text("ALTER TABLE public.news ALTER COLUMN fecha DROP NOT NULL"))
                    session.commit()
                    logger.info("✅ Migración de columna fecha completada (PostgreSQL)")
                else:
                    logger.info("⏭️ Columna fecha ya permite NULL (PostgreSQL)")
                
    except Exception as e:
        # Si la tabla no existe o ya está migrada, no es un error crítico
        logger.warning(f"⚠️ No se pudo migrar columna fecha (puede que ya esté migrada): {e}")

def init_database():
    """Inicializa la base de datos - función principal"""
    
    if not verify_database_connection():
        raise RuntimeError("No se pudo establecer conexión con la base de datos")
    
    try:
        create_sqlmodel_tables()          # 1. Crear tablas base
        migrate_news_fecha_column()       # 1.5. Migrar columna fecha si es necesario
        create_admin_user()               # 2. Crear admin
        create_public_initial_data()      # 3. Crear datos iniciales
        verify_admin_user()               # 4. Verificar admin
        
        if not is_sqlite:
            migrate_all_tenant_schemas()  # 5. Migrar tenants existentes (solo PostgreSQL)
        
    except Exception as e:
        logger.error(f"❌ Error crítico al inicializar base de datos: {e}")
        raise

def verify_admin_user():
    """Verifica si el usuario admin existe y muestra sus datos"""
    try:
        with Session(engine) as session:
            if is_sqlite:
                result = session.exec(
                    text("""
                        SELECT id, full_name, email, client
                        FROM user2 
                        WHERE email = :email
                    """).bindparams(email="admin@shirkasoft.com")
                )
            else:
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
# FUNCIONES PARA DATOS INICIALES (PLANTILLAS PARA TENANTS)
# =============================================================================

def create_initial_header():
    """Crea el registro inicial para el encabezado"""
    try:
        with Session(engine) as session:
            if is_sqlite:
                result = session.exec(text("SELECT COUNT(*) FROM header"))
            else:
                result = session.exec(text("SELECT COUNT(*) FROM public.header"))
            
            count = result.scalar()
            
            if count == 0:
                if is_sqlite:
                    session.exec(
                        text("""
                            INSERT INTO header (name, logo)
                            VALUES (:name, :logo)
                        """).bindparams(name="Encabezado", logo=None)
                    )
                else:
                    session.exec(
                        text("""
                            INSERT INTO public.header (name, logo)
                            VALUES (:name, :logo)
                        """).bindparams(name="Encabezado", logo=None)
                    )
                session.commit()
            else:
                logger.info("  ⏭️ Header ya existe")
    except Exception as e:
        logger.error(f"  ❌ Error al crear header inicial: {e}")
        raise

def create_initial_contact():
    """Crea el registro inicial para el contacto"""
    try:
        with Session(engine) as session:
            if is_sqlite:
                result = session.exec(text("SELECT COUNT(*) FROM contact"))
            else:
                result = session.exec(text("SELECT COUNT(*) FROM public.contact"))
            
            count = result.scalar()
            
            if count == 0:
                if is_sqlite:
                    session.exec(
                        text("""
                            INSERT INTO contact (email, address, social_networks)
                            VALUES (:email, :address, :social_networks)
                        """).bindparams(
                            email="example@email.com",
                            address=None,
                            social_networks=json.dumps(DEFAULT_SOCIAL_NETWORKS)
                        )
                    )
                else:
                    session.exec(
                        text("""
                            INSERT INTO public.contact (email, address, social_networks)
                            VALUES (:email, :address, :social_networks)
                        """).bindparams(
                            email="example@email.com",
                            address=None,
                            social_networks=json.dumps(DEFAULT_SOCIAL_NETWORKS)
                        )
                    )
                session.commit()
            else:
                logger.info("  ⏭️ Contact ya existe")
    except Exception as e:
        logger.error(f"  ❌ Error al crear contacto inicial: {e}")
        raise

def create_initial_company():
    """Crea los registros iniciales para company"""
    company_data = [
        {'title': 'Título 1', 'description': 'Descripción para el título 1.', 'photo': None, 'status': True},
        {'title': 'Título 2', 'description': 'Descripción para el título 2.', 'photo': None, 'status': True},
        {'title': 'Título 3', 'description': 'Descripción para el título 3.', 'photo': None, 'status': True},
    ]
    
    try:
        with Session(engine) as session:
            if is_sqlite:
                result = session.exec(text("SELECT COUNT(*) FROM company"))
            else:
                result = session.exec(text("SELECT COUNT(*) FROM public.company"))
            
            count = result.scalar()
            
            if count == 0:
                for data in company_data:
                    if is_sqlite:
                        session.exec(
                            text("""
                                INSERT INTO company (title, description, photo, status)
                                VALUES (:title, :description, :photo, :status)
                            """).bindparams(**data)
                        )
                    else:
                        session.exec(
                            text("""
                                INSERT INTO public.company (title, description, photo, status)
                                VALUES (:title, :description, :photo, :status)
                            """).bindparams(**data)
                        )
                session.commit()
            else:
                logger.info("  ⏭️ Companies ya existen")
    except Exception as e:
        logger.error(f"  ❌ Error al crear companies iniciales: {e}")
        raise

def create_initial_carrousels():
    """Crea registros iniciales para carrousel"""
    carrousel_data = [
        {"title": "Carrusel 1", "description": "Descripción del carrusel 1", 'photo': None, 'status': True},
        {"title": "Carrusel 2", "description": "Descripción del carrusel 2", 'photo': None, 'status': True},
        {"title": "Carrusel 3", "description": "Descripción del carrusel 3", 'photo': None, 'status': True},
        {"title": "Carrusel 4", "description": "Descripción del carrusel 4", 'photo': None, 'status': True},
        {"title": "Carrusel 5", "description": "Descripción del carrusel 5", 'photo': None, 'status': True},
    ]
    
    try:
        with Session(engine) as session:
            if is_sqlite:
                result = session.exec(text("SELECT COUNT(*) FROM carrousel"))
            else:
                result = session.exec(text("SELECT COUNT(*) FROM public.carrousel"))
            
            count = result.scalar()
            
            if count == 0:
                for data in carrousel_data:
                    if is_sqlite:
                        session.exec(
                            text("""
                                INSERT INTO carrousel (title, description, photo, status)
                                VALUES (:title, :description, :photo, :status)
                            """).bindparams(**data)
                        )
                    else:
                        session.exec(
                            text("""
                                INSERT INTO public.carrousel (title, description, photo, status)
                                VALUES (:title, :description, :photo, :status)
                            """).bindparams(**data)
                        )
                session.commit()
            else:
                logger.info("  ⏭️ Carrousels ya existen")
    except Exception as e:
        logger.error(f"  ❌ Error al crear carrousels iniciales: {e}")
        raise

# =============================================================================
# FUNCIONES MULTITENANT (SOLO POSTGRESQL)
# =============================================================================

def validate_schema_name(schema_name: str) -> bool:
    """Valida que el nombre del esquema sea seguro (previene SQL injection)"""
    if is_sqlite:
        # En SQLite, los esquemas no se usan, pero validamos igual por seguridad
        return bool(schema_name) and schema_name.strip() != ""
    
    pattern = r'^[a-zA-Z0-9_]{1,50}$'
    return bool(re.match(pattern, schema_name))

def get_all_tables_except_user():
    """Obtiene todas las tablas excepto user2 y active_sessions"""
    try:
        with Session(engine) as session:
            if is_sqlite:
                result = session.exec(text("""
                    SELECT name 
                    FROM sqlite_master 
                    WHERE type = 'table'
                    AND name NOT IN ('user2', 'active_sessions', 'chatbot_config', 'chatbot_usage', 'chatbot_model')
                    ORDER BY name
                """))
                tables = [row[0] for row in result.fetchall()]
            else:
                result = session.exec(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                    AND table_name NOT IN ('user2', 'active_sessions','chatbot_config', 'chatbot_usage', 'chatbot_model')
                    ORDER BY table_name
                """))
                tables = [row[0] for row in result.fetchall()]
            return tables
    except Exception as e:
        logger.error(f"Error al obtener lista de tablas: {e}")
        return []

def create_tenant_schema(client_name: str):
    """Crea un esquema para un nuevo tenant (solo para PostgreSQL)"""
    if is_sqlite:
        logger.info(f"⏭️ SQLite: Ignorando creación de esquema para '{client_name}' (no necesario)")
        return
    
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
                    # Crear tabla sin incluir defaults (para evitar dependencias de secuencias públicas)
                    session.exec(text(f"""
                        CREATE TABLE IF NOT EXISTS {client_name}.{table_name} 
                        (LIKE public.{table_name} INCLUDING CONSTRAINTS INCLUDING INDEXES)
                    """))
                    
                    # Crear secuencias específicas para este tenant
                    create_tenant_sequences(session, client_name, table_name)
                    
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

def create_tenant_sequences(session: Session, client_name: str, table_name: str):
    """Crea secuencias específicas para las tablas del tenant (solo PostgreSQL)"""
    if is_sqlite:
        return  # SQLite no usa secuencias
    
    # Obtener columnas seriales de la tabla
    result = session.exec(text("""
        SELECT column_name, column_default 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = :table_name 
        AND column_default LIKE 'nextval%'
    """).bindparams(table_name=table_name))
    
    for row in result:
        column_name, default_value = row
        # Extraer el nombre de la secuencia del valor por defecto
        seq_match = re.search(r"nextval\('([^']+)'::regclass\)", default_value)
        if seq_match:
            public_seq_name = seq_match.group(1)
            # Crear nombre de secuencia para el tenant
            tenant_seq_name = f"{client_name}.{public_seq_name.split('.')[-1]}"
            
            # Crear nueva secuencia
            session.exec(text(f"CREATE SEQUENCE IF NOT EXISTS {tenant_seq_name}"))
            
            # Asignar la nueva secuencia a la columna
            session.exec(text(f"""
                ALTER TABLE {client_name}.{table_name} 
                ALTER COLUMN {column_name} 
                SET DEFAULT nextval('{tenant_seq_name}')
            """))

def create_tenant_initial_data(client_name: str):
    """Copia TODOS los datos iniciales desde public a tenant automáticamente"""
    if is_sqlite:
        logger.info(f"⏭️ SQLite: Ignorando datos iniciales para '{client_name}' (no necesario)")
        return
    
    if not validate_schema_name(client_name):
        raise ValueError(f"Nombre de esquema inválido: {client_name}")
        
    try:
        with Session(engine) as session:
            logger.info(f"📊 Copiando todos los datos iniciales para tenant '{client_name}'...")
            
            # Lista específica de tablas que deben tener datos iniciales
            tables_with_initial_data = ['header', 'contact', 'company', 'carrousel']
            
            # Para SQLite, simplemente verificamos que las tablas tengan datos
            if is_sqlite:
                for table_name in tables_with_initial_data:
                    try:
                        # Verificar si la tabla tiene datos
                        count_result = session.exec(text(f"SELECT COUNT(*) FROM {table_name}"))
                        count = count_result.scalar()
                        
                        if count == 0:
                            # Si no hay datos, crear datos iniciales básicos
                            if table_name == 'header':
                                session.exec(
                                    text("INSERT INTO header (name, logo) VALUES (:name, :logo)")
                                    .bindparams(name=f"Encabezado {client_name}", logo=None)
                                )
                            elif table_name == 'contact':
                                session.exec(
                                    text("INSERT INTO contact (email, phone, address) VALUES (:email, :phone, :address)")
                                    .bindparams(
                                        email=f"contact@{client_name}.com",
                                        phone="+7 234 1234",
                                        address=None
                                    )
                                )
                            elif table_name == 'company':
                                # Crear una company básica
                                session.exec(
                                    text("INSERT INTO company (title, description, photo, status) VALUES (:title, :description, :photo, :status)")
                                    .bindparams(
                                        title=f"Compañía {client_name}",
                                        description=f"Descripción para {client_name}",
                                        photo=None,
                                        status=True
                                    )
                                )
                            elif table_name == 'carrousel':
                                # Crear un carrousel básico
                                session.exec(
                                    text("INSERT INTO carrousel (title, description, photo, status) VALUES (:title, :description, :photo, :status)")
                                    .bindparams(
                                        title=f"Carrusel {client_name}",
                                        description=f"Descripción del carrusel para {client_name}",
                                        photo=None,
                                        status=True
                                    )
                                )
                            
                            session.commit()
                            logger.info(f"  ✅ Datos iniciales creados para '{table_name}'")
                        else:
                            logger.info(f"  ⏭️ Tabla '{table_name}' ya tiene datos")
                            
                    except Exception as e:
                        logger.error(f"  ❌ Error al verificar/crear datos para '{table_name}': {e}")
                        continue
                
                return
            
            # Para PostgreSQL: copiar datos desde public
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
                        update_tenant_sequences(session, client_name, table_name)
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
    
def update_tenant_sequences(session: Session, client_name: str, table_name: str):
    """Actualiza las secuencias del tenant al valor máximo actual (solo PostgreSQL)"""
    if is_sqlite:
        return  # SQLite no usa secuencias
    
    # Obtener columnas seriales
    result = session.exec(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = :client_name 
        AND table_name = :table_name 
        AND column_default LIKE 'nextval%'
    """).bindparams(client_name=client_name, table_name=table_name))
    
    for row in result:
        column_name = row[0]
        # Obtener el valor máximo actual
        max_val_result = session.exec(text(f"""
            SELECT COALESCE(MAX({column_name}), 0) 
            FROM {client_name}.{table_name}
        """))
        max_val = max_val_result.scalar()
        
        # Obtener nombre de la secuencia
        seq_result = session.exec(text(f"""
            SELECT column_default 
            FROM information_schema.columns 
            WHERE table_schema = :client_name 
            AND table_name = :table_name 
            AND column_name = :column_name
        """).bindparams(client_name=client_name, table_name=table_name, column_name=column_name))
        
        seq_default = seq_result.scalar()
        seq_match = re.search(r"nextval\('([^']+)'::regclass\)", seq_default)
        if seq_match:
            seq_name = seq_match.group(1)
            # Actualizar la secuencia
            session.exec(text(f"SELECT setval('{seq_name}', {max_val})"))

def get_tenant_db(client_name: str) -> Generator:
    """Obtiene una sesión de base de datos para el tenant específico"""
    if not validate_schema_name(client_name):
        raise ValueError(f"Nombre de esquema inválido: {client_name}")
    
    with Session(engine) as session:
        # SQLite: sesión simple
        if is_sqlite:
            yield session
            return  # ⚠️ SALIR AQUÍ, NO EJECUTAR CÓDIGO POSTGRESQL
        
        # PostgreSQL: configurar search_path
        try:
            session.exec(text(f"SET search_path TO {client_name}, public"))
            yield session
        finally:
            session.exec(text("SET search_path TO public"))

def migrate_existing_tenant_schema(client_name: str):
    """Migra un esquema de tenant existente agregando tablas faltantes (solo PostgreSQL)"""
    if is_sqlite:
        logger.info(f"⏭️ SQLite: No se migran esquemas para '{client_name}'")
        create_tenant_initial_data(client_name)
        return
    
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
    """Migra todos los esquemas de tenant existentes (solo PostgreSQL)"""
    if is_sqlite:
        logger.info("⏭️ SQLite: No se migran esquemas")
        return
    
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
    
def drop_tenant_schema(schema_name: str):
    """Elimina un esquema tenant (solo para PostgreSQL)"""
    if is_sqlite:
        logger.info(f"⏭️ SQLite: Ignorando eliminación de esquema '{schema_name}' (no necesario)")
        return
    
    if not validate_schema_name(schema_name):
        raise ValueError(f"Nombre de esquema inválido: {schema_name}")
    
    try:
        with Session(engine) as session:
            # Verificar si el esquema existe
            schema_exists = session.exec(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.schemata 
                    WHERE schema_name = :schema_name
                )
            """).bindparams(schema_name=schema_name)).scalar()
            
            if not schema_exists:
                logger.warning(f"⚠️ Esquema '{schema_name}' no existe, no se puede eliminar")
                return
            
            # Verificar si hay otros usuarios usando este esquema
            users_with_same_client = session.exec(text("""
                SELECT COUNT(*) 
                FROM public.user2 
                WHERE client = :client_name
            """).bindparams(client_name=schema_name)).scalar()
            
            if users_with_same_client > 0:
                logger.warning(f"⚠️ Hay {users_with_same_client} usuario(s) usando el esquema '{schema_name}'. No se eliminará.")
                return
            
            # IMPORTANTE: No eliminar esquemas del sistema
            if schema_name in ['public', 'shirkasoft']:
                logger.warning(f"⚠️ No se puede eliminar el esquema del sistema '{schema_name}'")
                return
            
            # Eliminar el esquema (CASCADE eliminará todas las tablas dentro)
            logger.warning(f"🗑️ Eliminando esquema '{schema_name}'...")
            session.exec(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            session.commit()
            logger.info(f"✅ Esquema '{schema_name}' eliminado correctamente")
            
    except Exception as e:
        logger.error(f"❌ Error al eliminar esquema '{schema_name}': {e}")
        raise