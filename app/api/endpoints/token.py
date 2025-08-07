from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List
from fastapi import APIRouter, Depends, HTTPException, Form, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlmodel import Session, select, text
from app.models.wep_user_model import WepUserModel
from app.config.database import get_db, engine
from app.config.config import settings
import logging, json, os

logger = logging.getLogger(__name__)

router = APIRouter()

# Configuración de seguridad
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
ALGORITHM = "HS256"

# Lista de tokens de frontend permitidos (formato JSON como ALLOWED_HOSTS)
def parse_token_list(env_value: str) -> List[str]:
    """
    Parsea la lista de tokens desde el .env
    Soporta tanto formato JSON como string separado por comas (legacy)
    """
    logger.info(f"🔍 Parseando FRONT_TOKENS desde .env: {env_value[:100]}..." if env_value else "🔍 FRONT_TOKENS está vacío")
    
    if not env_value:
        logger.warning("⚠️ No hay tokens de frontend configurados")
        return []
    
    env_value = env_value.strip()
    
    # Intentar parsear como JSON primero
    if env_value.startswith('[') and env_value.endswith(']'):
        try:
            tokens = json.loads(env_value)
            logger.info(f"✅ FRONT_TOKENS parseado como JSON: {len(tokens)} tokens encontrados")
            return tokens
        except json.JSONDecodeError as e:
            logger.error(f"❌ Error parseando FRONT_TOKENS como JSON: {e}")
            return []
    
    # Fallback: parsear como string separado por comas
    tokens = [token.strip() for token in env_value.split(",") if token.strip()]
    logger.info(f"✅ FRONT_TOKENS parseado como CSV: {len(tokens)} tokens encontrados")
    return tokens

# Parsear tokens
FRONT_TOKENS = parse_token_list(os.getenv("FRONT_TOKENS", ""))

# Logging detallado de tokens cargados
logger.info(f"🚀 FRONT_TOKENS cargados: {len(FRONT_TOKENS)} tokens")
for i, token in enumerate(FRONT_TOKENS):
    logger.info(f"  Token {i}: {token[:30]}...{token[-10:]} (longitud: {len(token)})")

# Token legacy para compatibilidad hacia atrás
LEGACY_FRONT_TOKEN = os.getenv("FRONT_TOKEN", "")
if LEGACY_FRONT_TOKEN and LEGACY_FRONT_TOKEN not in FRONT_TOKENS:
    FRONT_TOKENS.append(LEGACY_FRONT_TOKEN)
    logger.info(f"📄 Token legacy agregado: {LEGACY_FRONT_TOKEN[:30]}...")

class MockUser:
    """Clase para crear usuarios mock desde tokens de frontend"""
    def __init__(self, client: str, email: str = None, full_name: str = None, user_id: str = None):
        self.client = client
        self.email = email or f"frontend@{client}.com"
        self.full_name = full_name or f"Frontend User - {client}"
        self.id = user_id or "frontend"
        self.password = "frontend"
        logger.debug(f"👤 MockUser creado: client={self.client}, email={self.email}, id={self.id}")

def decode_frontend_token(token: str) -> Dict[str, Any]:
    """
    Intenta decodificar un token de frontend usando la SECRET_KEY
    Retorna el payload si es válido, None si no se puede decodificar
    Los tokens de frontend no tienen expiración, por lo que deshabilitamos verify_exp
    """
    logger.debug(f"🔓 Intentando decodificar token: {token[:30]}...")
    
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False}  # Deshabilitar verificación de expiración
        )
        logger.info(f"✅ Token decodificado exitosamente: {payload}")
        return payload
    except JWTError as e:
        logger.error(f"❌ Error decodificando token frontend: {e}")
        logger.debug(f"   Token problemático: {token}")
        logger.debug(f"   SECRET_KEY usado: {settings.SECRET_KEY[:10]}...")
        return None

def create_mock_user_from_token(token: str) -> MockUser:
    """
    Crea un MockUser a partir de un token de frontend decodificado
    """
    logger.info(f"🏗️ Creando MockUser desde token: {token[:30]}...")
    
    payload = decode_frontend_token(token)
    logger.info(f"📦 Payload decodificado: {payload}")
    
    if payload:
        logger.info("✅ Payload válido, extrayendo información...")
        
        # Extraer información del payload
        client = payload.get("client", "default")
        email = payload.get("email", f"frontend@{client}.com")
        full_name = payload.get("full_name", f"Frontend User - {client}")
        user_id = payload.get("id", "frontend")
        
        logger.info(f"📋 Datos extraídos - client: {client}, email: {email}, full_name: {full_name}, user_id: {user_id}")
        
        mock_user = MockUser(
            client=client,
            email=email,
            full_name=full_name,
            user_id=str(user_id)
        )
        
        logger.info(f"✅ MockUser creado exitosamente para cliente: {client}")
        return mock_user
    else:
        # Si no se puede decodificar, crear usuario por defecto
        logger.warning("⚠️ No se pudo decodificar el token, usando valores por defecto")
        mock_user = MockUser(client="shirkasoft", email="shirkasoft", full_name="shirkasoft")
        logger.info("🔧 MockUser por defecto creado")
        return mock_user

# ----------------------------
# Función para generar token (login)
# ----------------------------

@router.post("/sign-in/")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    logger.info(f"🔐 Intento de login para email: {email}")
    
    # 1. Verificar si el usuario existe
    user = db.exec(
        select(WepUserModel).where(WepUserModel.email == email)
    ).first()
    
    if not user:
        logger.warning(f"❌ Email no encontrado: {email}")
        raise HTTPException(status_code=404, detail="Email no registrado")

    # 2. Verificar contraseña con bcrypt 
    if not bcrypt_context.verify(password, user.password):
        logger.warning(f"❌ Contraseña incorrecta para: {email}")
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")

    logger.info(f"✅ Login exitoso para: {email}, cliente: {user.client}")

    # 3. Generar token JWT firmado con HS256
    access_token = jwt.encode(
        {
            "id": str(user.id),
            "full_name": user.full_name,
            "email": user.email, 
            "client": user.client, 
            "exp": datetime.now(timezone.utc) + timedelta(minutes=60)
        },
        settings.SECRET_KEY,  
        algorithm=ALGORITHM
    )

    logger.info(f"🎫 Token generado para {email}: {access_token[:30]}...")
    return {"access_token": access_token, "token_type": "bearer"}

# ----------------------------
# Función para decodificar/validar token
# ----------------------------

async def verify_token(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    logger.info(f"🔍 Verificando token: {token[:30]}...")
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Primero verificamos si es uno de los tokens de frontend
    logger.debug(f"🔍 Verificando contra {len(FRONT_TOKENS)} tokens de frontend...")
    
    if token in FRONT_TOKENS:
        logger.info("🎯 ¡Token de frontend detectado!")
        token_index = FRONT_TOKENS.index(token)
        logger.info(f"📍 Token encontrado en índice: {token_index}")
        
        mock_user = create_mock_user_from_token(token)
        logger.info(f"👤 MockUser creado para cliente: {mock_user.client}")
        return mock_user
    else:
        logger.info("🔄 No es token de frontend, intentando decodificar como token de usuario...")
    
    try:
        # Decodificar el token de usuario normal
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        
        logger.debug(f"📦 Token de usuario decodificado: {payload}")
        
        email = payload.get("email")
        if email is None:
            logger.error("❌ Token sin email")
            raise credentials_exception

        # Verificar si el usuario existe
        user = db.exec(
            select(WepUserModel).where(WepUserModel.email == email)
        ).first()
        
        if user is None:
            logger.error(f"❌ Usuario no encontrado en BD: {email}")
            raise credentials_exception

        logger.info(f"✅ Token de usuario válido: {email}, cliente: {user.client}")
        return user

    except JWTError as e:
        logger.error(f"❌ Error decodificando token de usuario: {e}")
        raise credentials_exception

async def get_current_tenant(current_user: WepUserModel = Depends(verify_token)) -> str:
    tenant = current_user.client
    logger.info(f"🏢 Tenant actual: {tenant}")
    return tenant

def get_tenant_session(client_name: str = Depends(get_current_tenant)) -> Generator[Session, None, None]:
    """
    Dependencia que proporciona una sesión de base de datos configurada 
    para el esquema del tenant específico
    """
    logger.info(f"🗄️ Creando sesión para tenant: {client_name}")
    
    # Validar nombre del esquema
    if not client_name or not client_name.strip():
        logger.error("❌ Nombre de cliente inválido")
        raise HTTPException(
            status_code=400,
            detail="Nombre de cliente inválido"
        )
    
    # Crear sesión
    with Session(engine) as session:
        try:
            # Configurar search_path para el tenant
            logger.debug(f"🔧 Configurando search_path: {client_name}, public")
            session.exec(text(f"SET search_path TO {client_name}, public"))
            logger.debug(f"✅ Search path configurado: {client_name}, public")
            
            # Verificar que el esquema existe
            schema_check = session.exec(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.schemata 
                    WHERE schema_name = :schema_name
                )
            """).bindparams(schema_name=client_name)).scalar()
            
            if not schema_check:
                logger.error(f"❌ Esquema {client_name} no existe")
                raise HTTPException(
                    status_code=404,
                    detail=f"Esquema para cliente '{client_name}' no encontrado"
                )
            
            logger.info(f"✅ Esquema {client_name} verificado y sesión creada")
            yield session
            
        except HTTPException:
            # Re-lanzar excepciones HTTP
            raise
        except Exception as e:
            logger.error(f"💥 Error en sesión de tenant {client_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error de base de datos para cliente {client_name}"
            )
        finally:
            # Restaurar search_path por seguridad
            try:
                session.exec(text("SET search_path TO public"))
                logger.debug("🔧 Search path restaurado a public")
            except Exception as e:
                logger.warning(f"⚠️ Error al restaurar search_path: {e}")
