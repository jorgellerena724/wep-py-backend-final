from fastapi import APIRouter, Form, Depends, HTTPException, status
from typing import List, Optional
from sqlmodel import select, Session
from app.api.endpoints.token import get_tenant_session, verify_token
from app.models.wep_product_model import WepProductModel
from app.models.wep_user_model import WepUserModel
from app.models.wep_category_model import WepCategoryModel

router = APIRouter()

@router.post("/", response_model=WepCategoryModel)
async def create_category(
    title: str = Form(..., max_length=100),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):  
    try:
        existing = db.exec(select(WepCategoryModel).where(WepCategoryModel.title == title)).first()
        
        if existing:
            raise HTTPException(status_code=400, detail="Ya existe una categoría con ese nombre.")
        else:                                   
            # Crear registro
            category = WepCategoryModel(title=title)
            db.add(category)
            db.commit()
            db.merge(category)
            return category
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creando category: {str(e)}"
        )

@router.patch("/{category_id}/", response_model=WepCategoryModel)
async def update_category(
    category_id: int,
    title: Optional[str] = Form(..., max_length=100),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Obtener el header existente
        category = db.get(WepCategoryModel, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Categoría no encontrada.")
        
        if title is not None:
            existing = db.exec(select(WepCategoryModel).where(WepCategoryModel.title == title)).first()
            
            if existing:
                raise HTTPException(status_code=400, detail="Ya existe una categoría con ese nombre.")
            else:    
                category.title = title

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

@router.get("/", response_model=List[WepCategoryModel])
def get_categories(  # Cambié el nombre para evitar conflicto con la función get_category individual
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    source = getattr(current_user, 'source', 'unknown')
    
    if source == "website":
        # Solo devolver categorías que tienen productos asociados Y activos
        query = (
            select(WepCategoryModel)
            .join(WepProductModel, WepCategoryModel.id == WepProductModel.category_id)
            .where(WepProductModel.status == True)  # Solo productos activos
            .distinct()
            .order_by(WepCategoryModel.id)
        )
    else:
        # Para el dashboard, devolver todas las categorías
        query = select(WepCategoryModel).order_by(WepCategoryModel.id)
    
    return db.exec(query).all()

@router.get("/{category_id}/", response_model=WepCategoryModel)
def get_category(category_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)):

    category = db.get(WepCategoryModel, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="category no encontrado")
    return category

@router.delete("/{category_id}/", status_code=204)
def delete_category(
    category_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    category = db.get(WepCategoryModel, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    
    try:
        # Verificar si hay productos asociados a esta categoría
        productos_asociados = db.exec(
            select(WepProductModel)
            .where(WepProductModel.category_id == category_id and WepProductModel.status == True)
        ).first()
        
        if productos_asociados:
            raise HTTPException(
                status_code=400,
                detail="No se puede eliminar la categoría porque tiene productos asociados. "
                       "Elimine o cambie la categoría de los productos primero."
            )
        
        # Eliminar registro
        db.delete(category)
        db.commit()
        
    except HTTPException:
        db.rollback()
        raise  # Re-lanzar la excepción HTTP para que FastAPI la maneje
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando categoría: {str(e)}"
        )