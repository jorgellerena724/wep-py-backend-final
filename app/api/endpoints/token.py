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

# Token legacy para compatibilidad hacia atrás
LEGACY_FRONT_TOKEN = os.getenv("FRONT_TOKEN", "")
if LEGACY_FRONT_TOKEN and LEGACY_FRONT_TOKEN not in FRONT_TOKENS:
    FRONT_TOKENS.append(LEGACY_FRONT_TOKEN)

class MockUser:
    """Clase para crear usuarios mock desde tokens de frontend"""
    def __init__(self, client: str, email: str = None, full_name: str = None, user_id: str = None):
        self.client = client
        self.email = email or f"frontend@{client}.com"
        self.full_name = full_name or f"Frontend User - {client}"
        self.id = user_id or "frontend"
        self.password = "frontend"

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
        return payload
    except JWTError as e:
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
              
        mock_user = MockUser(
            client=client,
            email=email,
            full_name=full_name,
            user_id=str(user_id)
        )
        
        return mock_user
    else:
        # Si no se puede decodificar, crear usuario por defecto
        mock_user = MockUser(client="shirkasoft", email="shirkasoft", full_name="shirkasoft")
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
    
    # 1. Verificar si el usuario existe
    user = db.exec(
        select(WepUserModel).where(WepUserModel.email == email)
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Email no registrado")

    # 2. Verificar contraseña con bcrypt 
    if not bcrypt_context.verify(password, user.password):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")

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

    return {"access_token": access_token, "token_type": "bearer"}

# ----------------------------
# Función para decodificar/validar token
# ----------------------------

async def verify_token(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Primero verificamos si es uno de los tokens de frontend
    
    if token in FRONT_TOKENS:
        
        mock_user = create_mock_user_from_token(token)
        return mock_user
    
    try:
        # Decodificar el token de usuario normal
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        
        email = payload.get("email")
        if email is None:
            raise credentials_exception

        # Verificar si el usuario existe
        user = db.exec(
            select(WepUserModel).where(WepUserModel.email == email)
        ).first()
        
        if user is None:
            raise credentials_exception

        return user

    except JWTError as e:
        raise credentials_exception

async def get_current_tenant(current_user: WepUserModel = Depends(verify_token)) -> str:
    tenant = current_user.client
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
            
            yield session
            
        except HTTPException:
            # Re-lanzar excepciones HTTP
            raise
        except Exception as e:
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
