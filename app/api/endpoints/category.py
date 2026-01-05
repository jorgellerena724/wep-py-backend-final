from fastapi import APIRouter, Form, Depends, HTTPException, status
from typing import Optional
from sqlmodel import select, Session
from app.api.endpoints.token import get_tenant_session, verify_token
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

@router.patch("/{category_id}", response_model=WepCategoryModel)
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

@router.get("/", response_model=list[WepCategoryModel])
def get_category( current_user: WepUserModel = Depends(verify_token),db: Session = Depends(get_tenant_session)):
    return db.exec(select(WepCategoryModel).order_by(WepCategoryModel.id)).all()

@router.get("/{category_id}", response_model=WepCategoryModel)
def get_category(category_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)):

    category = db.get(WepCategoryModel, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="category no encontrado")
    return category

@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, current_user: WepUserModel = Depends(verify_token),
     db: Session = Depends(get_tenant_session)):
    
    category = db.get(WepCategoryModel, category_id)
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