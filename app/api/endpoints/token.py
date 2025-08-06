from datetime import datetime, timedelta, timezone
import os
from typing import Generator
from fastapi import APIRouter, Depends, HTTPException, Form, logger, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlmodel import Session, select, text
from app.models.wep_user_model import WepUserModel
from app.config.database import get_db, engine
from app.config.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Configuración de seguridad
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
ALGORITHM = "HS256"
FRONT_TOKEN = os.getenv("FRONT_TOKEN", "default_front_token")


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
        {"id":str(user.id),"full_name":user.full_name,"email": user.email, "client": user.client, "exp": datetime.now(timezone.utc) + timedelta(minutes=60)},
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

     # Primero verificamos si es el token estático del frontend
    if token == FRONT_TOKEN:
        # Creamos un usuario mock con los datos requeridos
        class MockUser:
            email = "shirkasoft"
            password = "shirkasoft"
            full_name = "shirkasoft"
        
        return MockUser()
    
    
    try:
        # Decodificar el token
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

    except JWTError:
        raise credentials_exception
    
async def get_current_tenant(current_user: WepUserModel = Depends(verify_token)) -> str:
    return current_user.client

def get_tenant_session(client_name: str = Depends(get_current_tenant)) -> Generator[Session, None, None]:
    """
    Dependencia que proporciona una sesión de base de datos configurada 
    para el esquema del tenant específico
    """
    logger.info(f"Creando sesión para tenant: {client_name}")
    
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
            logger.debug(f"Search path configurado: {client_name}, public")
            
            # Verificar que el esquema existe
            schema_check = session.exec(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.schemata 
                    WHERE schema_name = :schema_name
                )
            """).bindparams(schema_name=client_name)).scalar()
            
            if not schema_check:
                logger.error(f"Esquema {client_name} no existe")
                raise HTTPException(
                    status_code=404,
                    detail=f"Esquema para cliente '{client_name}' no encontrado"
                )
            
            yield session
            
        except HTTPException:
            # Re-lanzar excepciones HTTP
            raise
        except Exception as e:
            logger.error(f"Error en sesión de tenant {client_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error de base de datos para cliente {client_name}"
            )
        finally:
            # Restaurar search_path por seguridad
            try:
                session.exec(text("SET search_path TO public"))
            except Exception as e:
                logger.warning(f"Error al restaurar search_path: {e}")
