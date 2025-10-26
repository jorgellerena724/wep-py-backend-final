from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List
from fastapi import APIRouter, Depends, HTTPException, Form, logger, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlmodel import Session, select, text
from app.models.wep_user_model import WepUserModel
from app.config.database import get_db, engine
from app.config.config import settings
import logging, json, os

router = APIRouter()

# Configurar logging para debug
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de seguridad
# Usar bcrypt directamente en lugar de passlib para evitar incompatibilidades
import bcrypt

bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verificar password usando bcrypt directamente"""
    logger.info(f"🔐 Verificando password con función verify_password")
    logger.info(f"🔐 Hash recibido: {hashed_password[:30]}...")
    
    try:
        # Intentar con passlib primero
        logger.info("🔄 Intentando verificación con passlib...")
        result = bcrypt_context.verify(plain_password, hashed_password)
        logger.info(f"✅ Verificación con passlib: {result}")
        return result
    except (ValueError, AttributeError, Exception) as e:
        logger.warning(f"⚠️ Error con passlib: {type(e).__name__} - {e}")
        logger.info("🔄 Intentando con bcrypt directo...")
        # Fallback: usar bcrypt directamente
        try:
            # Truncar password si es necesario
            password_bytes = plain_password.encode('utf-8')
            if len(password_bytes) > 72:
                logger.warning(f"⚠️ Truncando password a 72 bytes")
                password_bytes = password_bytes[:72]
            
            # El hash ya está en bytes o string, verificar
            if isinstance(hashed_password, str):
                hash_bytes = hashed_password.encode('utf-8')
            else:
                hash_bytes = hashed_password
                
            result = bcrypt.checkpw(password_bytes, hash_bytes)
            logger.info(f"✅ Verificación con bcrypt directo: {result}")
            return result
        except Exception as e2:
            logger.error(f"❌ Error verificando con bcrypt directo: {type(e2).__name__} - {e2}")
            return False
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
ALGORITHM = "HS256"

# Lista de tokens de frontend permitidos (formato JSON como ALLOWED_HOSTS)
def parse_token_list(env_value: str) -> List[str]:
    """
    Parsea la lista de tokens desde el .env
    Soporta tanto formato JSON como string separado por comas (legacy)
    """  
    if not env_value:
        return []
    
    env_value = env_value.strip()
    
    # Intentar parsear como JSON primero
    if env_value.startswith('[') and env_value.endswith(']'):
        try:
            tokens = json.loads(env_value)
            return tokens
        except json.JSONDecodeError as e:
            return []
    
    # Fallback: parsear como string separado por comas
    tokens = [token.strip() for token in env_value.split(",") if token.strip()]
    return tokens

# Parsear tokens
FRONT_TOKENS = parse_token_list(os.getenv("FRONT_TOKENS", ""))

class MockUser:
    """Clase para crear usuarios mock desde tokens de frontend"""
    def __init__(self, client: str, email: str = None, full_name: str = None, user_id: str = None, source: str = None):
        self.client = client
        self.email = email or f"frontend@{client}.com"
        self.full_name = full_name or f"Frontend User - {client}"
        self.id = user_id or "frontend"
        self.source = source or "unknown"  # Valor por defecto
        self.password = "frontend"
        
        # Log para debug
        logger.info(f"🔧 MockUser creado - client: {self.client}, source: {self.source}, email: {self.email}")

def decode_frontend_token(token: str) -> Dict[str, Any]:
    """
    Intenta decodificar un token de frontend usando la SECRET_KEY
    Retorna el payload si es válido, None si no se puede decodificar
    Los tokens de frontend no tienen expiración, por lo que deshabilitamos verify_exp
    """
    
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False}  # Deshabilitar verificación de expiración
        )
        logger.info(f"🔓 Token decodificado exitosamente: {payload}")
        return payload
    except JWTError as e:
        logger.warning(f"⚠️ Error decodificando token: {e}")
        return None

def create_mock_user_from_token(token: str) -> MockUser:
    """
    Crea un MockUser a partir de un token de frontend decodificado
    """
    
    payload = decode_frontend_token(token)
    
    if payload:
        
        # Extraer información del payload
        client = payload.get("client", "default")
        email = payload.get("email", f"frontend@{client}.com")
        full_name = payload.get("full_name", f"Frontend User - {client}")
        user_id = payload.get("id", "frontend")
        source = payload.get("source", "website")
        
        logger.info(f"📝 Creando MockUser con datos del payload:")
        logger.info(f"   - client: {client}")
        logger.info(f"   - email: {email}")
        logger.info(f"   - source: {source}")
        logger.info(f"   - user_id: {user_id}")
              
        mock_user = MockUser(
            client=client,
            email=email,
            full_name=full_name,
            user_id=str(user_id),
            source=source
        )
        
        return mock_user
    else:
        # Si no se puede decodificar, crear usuario por defecto
        logger.warning("⚠️ No se pudo decodificar el token, creando usuario por defecto")
        mock_user = MockUser(client="shirkasoft", email="shirkasoft", full_name="shirkasoft")
        return mock_user

# Función auxiliar para crear usuario extendido desde payload JWT
class ExtendedUser:
    """Clase para usuarios reales con campos adicionales del JWT"""
    def __init__(self, user: WepUserModel, source: str = None):
        # Copiar todos los atributos del usuario original
        for attr in dir(user):
            if not attr.startswith('_'):
                setattr(self, attr, getattr(user, attr))
        
        # Agregar el campo source
        self.source = source or "dashboard"
        
        logger.info(f"👤 ExtendedUser creado - email: {self.email}, source: {self.source}, client: {self.client}")

# ----------------------------
# Función para generar token (login)
# ----------------------------

@router.post("/sign-in/")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    
    logger.info("=" * 60)
    logger.info("🔐 INICIANDO PROCESO DE LOGIN")
    logger.info(f"📧 Email recibido: {email}")
    logger.info(f"🔑 Password recibido: {'*' * len(password)} (longitud: {len(password)})")
    logger.info("=" * 60)
    
    # 1. Verificar si el usuario existe
    logger.info("🔍 Buscando usuario en base de datos...")
    user = db.exec(
        select(WepUserModel).where(WepUserModel.email == email)
    ).first()
    
    if not user:
        logger.error(f"❌ Usuario no encontrado: {email}")
        raise HTTPException(status_code=404, detail="Email no registrado")
    
    logger.info(f"✅ Usuario encontrado: {user.full_name}")
    logger.info(f"📋 Usuario ID: {user.id}")
    logger.info(f"🏢 Usuario Client: {user.client}")

    # 2. Verificar contraseña con bcrypt 
    logger.info(f"🔍 Verificando contraseña para usuario: {email}")
    logger.info(f"🔍 Longitud de password ingresado: {len(password)} caracteres")
    logger.info(f"🔍 Hash almacenado comienza con: {user.password[:20] if user.password else 'None'}...")
    
    try:
        # Truncar password a 72 bytes si es necesario (limitación de bcrypt)
        password_bytes = password.encode('utf-8')
        if len(password_bytes) > 72:
            logger.warning(f"⚠️ Password truncado a 72 bytes (original: {len(password_bytes)} bytes)")
            password_bytes = password_bytes[:72]
        
        is_valid = verify_password(password, user.password)
        logger.info(f"🔍 Resultado verificación: {is_valid}")
        
        if not is_valid:
            raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error verificando contraseña: {e}")
        logger.error(f"❌ Tipo de error: {type(e).__name__}")
        raise HTTPException(status_code=401, detail="Error al verificar contraseña")

    # 3. Generar token JWT firmado con HS256
    logger.info("🎫 Generando token JWT...")
    token_payload = {
        "id": str(user.id),
        "full_name": user.full_name,
        "email": user.email, 
        "client": user.client, 
        "source": "dashboard",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60)
    }
    logger.info(f"📄 Token payload: {token_payload}")
    
    access_token = jwt.encode(
        token_payload,
        settings.SECRET_KEY,  
        algorithm=ALGORITHM
    )
    
    logger.info("✅ Token generado exitosamente")
    logger.info(f"🎫 Token (primeros 50 chars): {access_token[:50]}...")
    logger.info("=" * 60)
    logger.info("✅ LOGIN EXITOSO")
    logger.info("=" * 60)

    return {"access_token": access_token, "token_type": "bearer"}

# ----------------------------
# Función para decodificar/validar token
# ----------------------------

async def verify_token(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    
    logger.info(f"🔍 Verificando token: {token[:50]}...")  # Solo primeros 50 chars por seguridad
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # NUEVO: Intentamos decodificar cualquier token JWT primero
    try:
        # Decodificar sin verificar expiración para analizar el contenido
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False}
        )
        
        logger.info(f"✅ Token JWT decodificado exitosamente")
        logger.info(f"📄 Payload: {payload}")
        
        # Obtener el source del payload
        source = payload.get("source", "dashboard")
        email = payload.get("email")
        
        logger.info(f"🏷️ Source detectado: '{source}'")
        logger.info(f"📧 Email detectado: '{email}'")
        
        # CASE 1: Token de WEBSITE (no verificar expiración, crear MockUser)
        if source == "website":
            logger.info("🌐 TOKEN DE WEBSITE DETECTADO - Creando MockUser")
            
            # Para tokens de website, crear MockUser directamente del payload
            client = payload.get("client", "default")
            full_name = payload.get("full_name", f"Website User - {client}")
            user_id = payload.get("id", "website")
            
            mock_user = MockUser(
                client=client,
                email=email or f"website@{client}.com",
                full_name=full_name,
                user_id=str(user_id),
                source=source
            )
            
            logger.info(f"✅ MockUser creado para website - client: {mock_user.client}, source: {mock_user.source}")
            return mock_user
        
        # CASE 2: Token de DASHBOARD (verificar expiración y usuario en BD)
        else:
            logger.info("🏢 TOKEN DE DASHBOARD DETECTADO - Validando usuario real")
            
            # Para tokens de dashboard, verificar expiración
            try:
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=[ALGORITHM]
                    # verify_exp=True por defecto
                )
                logger.info("✅ Token de dashboard válido (no expirado)")
            except JWTError as e:
                logger.warning(f"⚠️ Token de dashboard expirado: {e}")
                raise credentials_exception
            
            if email is None:
                logger.warning("⚠️ Token de dashboard sin email")
                raise credentials_exception

            # Verificar si el usuario existe en la BD
            user = db.exec(
                select(WepUserModel).where(WepUserModel.email == email)
            ).first()
            
            if user is None:
                logger.warning(f"⚠️ Usuario de dashboard no encontrado: {email}")
                raise credentials_exception

            # Crear ExtendedUser con el campo source del JWT
            extended_user = ExtendedUser(user, source)
            logger.info(f"✅ ExtendedUser creado para dashboard - email: {extended_user.email}, source: {extended_user.source}")
            return extended_user
        
    except JWTError as e:
        logger.warning(f"⚠️ No es un JWT válido: {e}")
        
        # FALLBACK: Verificar si está en FRONT_TOKENS (sistema legacy)
        if token in FRONT_TOKENS:
            logger.info("📋 Token encontrado en FRONT_TOKENS (legacy)")
            mock_user = create_mock_user_from_token(token)
            return mock_user
        
        logger.error("❌ Token completamente inválido")
        raise credentials_exception

async def get_current_tenant(current_user = Depends(verify_token)) -> str:
    tenant = current_user.client
    logger.info(f"🏢 Tenant actual: {tenant}")
    return tenant

def get_tenant_session(client_name: str = Depends(get_current_tenant)) -> Generator[Session, None, None]:
    """
    Dependencia que proporciona una sesión de base de datos configurada 
    para el esquema del tenant específico
    """
    
    # Validar nombre del esquema
    if not client_name or not client_name.strip():
        raise HTTPException(
            status_code=400,
            detail="Nombre de cliente inválido"
        )
    
    logger.info(f"🔌 Conectando a esquema: {client_name}")
    
    # Crear sesión
    with Session(engine) as session:
        try:
            # Configurar search_path para el tenant
            session.exec(text(f"SET search_path TO {client_name}, public"))
            
            # Verificar que el esquema existe
            schema_check = session.exec(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.schemata 
                    WHERE schema_name = :schema_name
                )
            """).bindparams(schema_name=client_name)).scalar()
            
            if not schema_check:
                raise HTTPException(
                    status_code=404,
                    detail=f"Esquema para cliente '{client_name}' no encontrado"
                )
            
            logger.info(f"✅ Conectado exitosamente al esquema: {client_name}")
            yield session
            
        except HTTPException:
            # Re-lanzar excepciones HTTP
            raise
        except Exception as e:
            logger.error(f"❌ Error de base de datos para cliente {client_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error de base de datos para cliente {client_name}"
            )
        finally:
            # Restaurar search_path por seguridad
            try:
                session.exec(text("SET search_path TO public"))
            except Exception as e:
                logger.warning(f"⚠️ Error al restaurar search_path: {e}")