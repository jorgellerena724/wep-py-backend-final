from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Form, logger, status
from sqlmodel import SQLModel, Session, select
from passlib.context import CryptContext
from app.api.endpoints.token import verify_token
from app.models.wep_user_model import WepUserModel
from app.config.database import create_tenant_schema, get_db
from app.config.config import settings

router = APIRouter()
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserResponse(SQLModel):
    id: int
    email: str
    full_name: str
    client: str

# Modelo para actualización (PATCH)
class UserUpdateRequest(SQLModel):
    email: Optional[str] = None
    password: Optional[str] = None
    full_name: Optional[str] = None
    client: Optional[str] = None

class UserCreateRequest(SQLModel):
    email: str
    password: str
    full_name: str
    client: str

# --- READ
@router.get("/", response_model=List[WepUserModel])
def get_user(
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_db)
):
    statement = select(WepUserModel).order_by(WepUserModel.id)  # Orden aplicado aquí
    users = db.exec(statement).all()  
    
    if not users:
        raise HTTPException(status_code=404, detail="Usuarios no encontrados")
    
    return users

# --- CREATE
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreateRequest,
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_db)
):
    # 1. Verificar si el email ya existe
    existing_user = db.exec(
        select(WepUserModel).where(WepUserModel.email == user_data.email)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya está registrado"
        )
    # 2. Crear esquema del cliente si no existe
    try:
        create_tenant_schema(user_data.client)
    except Exception as e:
        logger.warning(f"Esquema '{user_data.client}' ya existe o error: {e}")

    # 3. Hashear la contraseña con bcrypt
    hashed_password = bcrypt_context.hash(user_data.password)

    # 4. Crear el usuario
    new_user = WepUserModel(
        email=user_data.email,
        password=hashed_password,  
        full_name=user_data.full_name,
        client=user_data.client
    )

    db.add(new_user)
    db.commit()
    db.merge(new_user)

    return {
        "message": "Usuario creado exitosamente",
        "email": new_user.email,
        "full_name": new_user.full_name,
        "client": new_user.client
    }

# --- UPDATE ---
@router.patch("/{user_id}")
async def update_user(
    user_id: int,
    user_data: UserUpdateRequest,
    current_user: WepUserModel = Depends(verify_token),  
    db: Session = Depends(get_db)
):
    # 1. Buscar el usuario a modificar
    user = db.get(WepUserModel, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # 2. Actualizar campos 
    if user_data.email:
        existing_user = db.exec(
            select(WepUserModel).where(WepUserModel.email == user_data.email)
        ).first()
        if existing_user and existing_user.id != user_id:
            raise HTTPException(status_code=400, detail="El email ya está en uso")
        user.email = user_data.email

    if user_data.full_name:
        user.full_name = user_data.full_name

    if user_data.password:
        user.password = bcrypt_context.hash(user_data.password)

    # 3. Guardar cambios
    db.add(user)
    db.commit()
    db.merge(user)

    return {
        "message": "Usuario actualizado",
        "email": user.email,
        "full_name": user.full_name
    }


# --- DELETE ---
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: WepUserModel = Depends(verify_token),  
    db: Session = Depends(get_db)
):
    # 1. Buscar el usuario a eliminar
    user = db.get(WepUserModel, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # 2. No permitir eliminar el usuario admin principal
    if user.email == "admin@shirkasoft.com":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar el usuario administrador principal"
        )
    
    # 3. Guardar el nombre del client para verificar después
    client_to_check = user.client
    
    # 4. Eliminar el usuario
    db.delete(user)
    db.commit()
    
    # 5. Verificar si se debe eliminar el esquema tenant
    try:
        # Contar cuántos usuarios quedan con este mismo client
        remaining_users = db.exec(
            select(WepUserModel).where(WepUserModel.client == client_to_check)
        ).all()
        
        # Si no quedan usuarios con este client, eliminar el esquema
        if len(remaining_users) == 0:
            from app.config.database import drop_tenant_schema, is_sqlite_db
            
            # Solo eliminar esquema si NO es SQLite
            if not is_sqlite_db():
                # Verificar que no sea un esquema del sistema
                if client_to_check and client_to_check not in ['public', 'shirkasoft']:
                    drop_tenant_schema(client_to_check)
            else:
                logger.info(f"⏭️ SQLite: No se elimina esquema para '{client_to_check}'")
                
    except Exception as e:
        # No fallar la operación principal si hay error al eliminar el esquema
        logger.error(f"⚠️ Error al intentar eliminar esquema: {e}")
    
    return None