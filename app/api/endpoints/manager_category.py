from fastapi import APIRouter, Form, Depends, HTTPException, status
from typing import Optional
from sqlmodel import select, Session, text
from app.api.endpoints.token import get_tenant_session, verify_token
from app.models.wep_user_model import WepUserModel
from app.models import WepManagerCategoryModel
from app.config.database import is_sqlite
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/", response_model=WepManagerCategoryModel)
async def create_category(
    title: str = Form(..., max_length=100),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):  
    try:
        client = getattr(current_user, 'client', 'N/A')
        logger.info(f"📝 Creando manager_category con título: '{title}'")
        logger.info(f"👤 Usuario: {current_user.email}, Client: {client}")
        
        # Verificar que la tabla existe (solo para debug)
        try:
            if not is_sqlite:
                # Verificar que la tabla existe en el esquema actual
                result = db.exec(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = current_schema()
                        AND table_name = 'manager_category'
                    )
                """))
                table_exists = result.scalar()
                logger.info(f"🔍 Tabla manager_category existe en esquema actual: {table_exists}")
        
        except Exception as check_error:
            logger.warning(f"⚠️ No se pudo verificar existencia de tabla: {check_error}")
        
        # Crear registro
        category = WepManagerCategoryModel(title=title)
        db.add(category)
        db.flush()  # Flush para obtener el ID sin hacer commit completo
        
        logger.info(f"✅ Categoría agregada a la sesión, ID: {category.id}")
        
        # Hacer commit
        db.commit()
        logger.info(f"✅ Commit realizado exitosamente")
        
        # Refrescar el objeto desde la base de datos para asegurar que tenemos todos los datos
        db.refresh(category)
        logger.info(f"✅ Categoría refrescada, ID final: {category.id}, Título: {category.title}")
        
        # Verificar que realmente se guardó consultando de nuevo
        try:
            saved_category = db.exec(
                select(WepManagerCategoryModel).where(WepManagerCategoryModel.id == category.id)
            ).first()
            if saved_category:
                logger.info(f"✅ Verificación: Categoría encontrada en BD con ID {saved_category.id}")
            else:
                logger.error(f"❌ Verificación: Categoría NO encontrada en BD después del commit!")
        except Exception as verify_error:
            logger.warning(f"⚠️ Error verificando categoría guardada: {verify_error}")
        
        return category
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creando category: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creando category: {str(e)}"
        )

@router.patch("/{category_id}", response_model=WepManagerCategoryModel)
async def update_category(
    category_id: int,
    title: Optional[str] = Form(..., max_length=100),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Obtener el header existente
        category = db.get(WepManagerCategoryModel, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="category no encontrado")

        # Actualizar nombre si se proporciona
        if title is not None:
            category.title = title

        # Confirmar cambios en la base de datos
        db.commit()
        db.merge(category)
        
        return category

    except HTTPException:
        # Re-lanzar excepciones HTTP que ya estamos manejando
        db.rollback()
        raise

    except Exception as e:
        # Revertir cambios en caso de cualquier otro error
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el category: {str(e)}"
        )

@router.get("/", response_model=list[WepManagerCategoryModel])
def get_category( current_user: WepUserModel = Depends(verify_token),db: Session = Depends(get_tenant_session)):
    return db.exec(select(WepManagerCategoryModel).order_by(WepManagerCategoryModel.id)).all()

@router.get("/{category_id}", response_model=WepManagerCategoryModel)
def get_category(category_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)):

    category = db.get(WepManagerCategoryModel, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="category no encontrado")
    return category

@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, current_user: WepUserModel = Depends(verify_token),
     db: Session = Depends(get_tenant_session)):
    
    category = db.get(WepManagerCategoryModel, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="category no encontrado")
    
    try:
        
        # Eliminar registro
        db.delete(category)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando category: {str(e)}"
        )