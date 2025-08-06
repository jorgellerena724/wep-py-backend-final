from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, status
from typing import Optional
from sqlmodel import select, Session
from app.api.endpoints.token import verify_token, get_tenant_session
from app.models.wep_user_model import WepUserModel
from app.models.wep_reviews_model import WepReviewsModel
from app.services.file_service import FileService
from sqlalchemy.orm import Session

router = APIRouter()

@router.post("/", response_model=WepReviewsModel)
async def create_reviews(
    title: str = Form(..., max_length=100),
    description: str = Form(...),
    photo: UploadFile = Form(...),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    # Validar imagen
    FileService.validate_file(photo)
    
    try:
        # Guardar imagen (solo nombre)
        photo_filename = await FileService.save_file(photo)
        
        # Crear registro
        reviews = WepReviewsModel(title=title, description=description, photo=photo_filename)
        db.add(reviews)
        db.commit()
        db.refresh(reviews)
        return reviews
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creando reviews: {str(e)}"
        )


@router.patch("/{reviews_id}", response_model=WepReviewsModel)
async def update_reviews(
    reviews_id: int,
    title: Optional[str] = Form(..., max_length=100),
    description: Optional[str] = Form(...),
    photo: Optional[UploadFile] = Form(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Obtener el header existente
        reviews = db.get(WepReviewsModel, reviews_id)
        if not reviews:
            raise HTTPException(status_code=404, detail="Reviews no encontrado")

        # Actualizar nombre si se proporciona
        if title is not None:
            reviews.title = title

        
        # Actualizar descripcion si se proporciona
        if description is not None:
            reviews.description = description

        # Procesar imagen si se proporciona
        if photo is not None:
            # Validar tipo de imagen
            FileService.validate_file(photo)
            
            # Eliminar imagen anterior si existe
            if reviews.photo:
                FileService.delete_file(reviews.photo, current_user.client)
            
            # Guardar nueva imagen
            new_filename = await FileService.save_file(photo)
            reviews.photo = new_filename

        # Confirmar cambios en la base de datos
        db.commit()
        db.refresh(reviews)
        
        return reviews

    except HTTPException:
        # Re-lanzar excepciones HTTP que ya estamos manejando
        db.rollback()
        raise

    except Exception as e:
        # Revertir cambios en caso de cualquier otro error
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el reviews: {str(e)}"
        )

@router.get("/", response_model=list[WepReviewsModel])
def get_reviews( current_user: WepUserModel = Depends(verify_token),db: Session = Depends(get_tenant_session)):
    return db.exec(select(WepReviewsModel).order_by(WepReviewsModel.id)).all()

@router.get("/{reviews_id}", response_model=WepReviewsModel)
def get_reviews(reviews_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)):

    reviews = db.get(WepReviewsModel,reviews_id)
    if not reviews:
        raise HTTPException(status_code=404, detail="Reviews no encontrado")
    return reviews

@router.delete("/{reviews_id}", status_code=204)
def delete_reviews(reviews_id: int, current_user: WepUserModel = Depends(verify_token),
     db: Session = Depends(get_tenant_session)):
    
    reviews = db.get(WepReviewsModel, reviews_id)
    if not reviews:
        raise HTTPException(status_code=404, detail="Reviews no encontrado")
    
    try:
        # Eliminar imagen asociada
        FileService.delete_file(reviews.photo, current_user.client)
        
        # Eliminar registro
        db.delete(reviews)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando reviews: {str(e)}"
        )