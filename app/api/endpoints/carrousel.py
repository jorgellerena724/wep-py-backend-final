from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException
from typing import Optional
from sqlmodel import select, Session
from app.api.endpoints.token import get_tenant_session, verify_token
from app.models.wep_user_model import WepUserModel
from app.models.wep_carrousel_model import WepCarrouselModel
from app.services.file_service import FileService

router = APIRouter()

@router.post("/", response_model=WepCarrouselModel)
async def create_header(
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
        photo_filename = await FileService.save_file(photo, current_user.client)
        
        # Crear registro
        carrousel = WepCarrouselModel(title=title, description=description, photo=photo_filename)
        db.add(carrousel)
        db.commit()
        db.refresh(carrousel)
        return carrousel
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creando carrousel: {str(e)}"
        )


@router.patch("/{carrousel_id}", response_model=WepCarrouselModel)
async def update_carrousel(
    carrousel_id: int,
    title: Optional[str] = Form(None, max_length=100),
    description: Optional[str] = Form(None),
    photo: Optional[UploadFile] = Form(None),
    status: Optional[bool] = Form(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Obtener el header existente
        carrousel = db.get(WepCarrouselModel, carrousel_id)
        if not carrousel:
            raise HTTPException(status_code=404, detail="Carrousel no encontrado")

        # Actualizar nombre si se proporciona
        if title is not None:
            carrousel.title = title

         # Actualizar descripcion si se proporciona
        if description is not None:
            carrousel.description = description
            
        if status is not None:
            carrousel.status = status

        # Procesar imagen si se proporciona
        if photo is not None:
            # Validar tipo de imagen
            FileService.validate_file(photo)
            
            # Eliminar imagen anterior si existe
            if carrousel.photo:
                FileService.delete_file(carrousel.photo, current_user.client)
            
            # Guardar nueva imagen
            new_filename = await FileService.save_file(photo, current_user.client)
            carrousel.photo = new_filename

        # Confirmar cambios en la base de datos
        db.commit()
        db.refresh(carrousel)
        
        return carrousel

    except HTTPException:
        # Re-lanzar excepciones HTTP que ya estamos manejando
        db.rollback()
        raise

    except Exception as e:
        # Revertir cambios en caso de cualquier otro error
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el carrousel: {str(e)}"
        )

@router.get("/", response_model=list[WepCarrouselModel])
def get_carrousel( current_user: WepUserModel = Depends(verify_token),db: Session = Depends(get_tenant_session)):
    
    source = getattr(current_user, 'source', 'unknown')
    
    if source == "website":
        query = select(WepCarrouselModel).where(WepCarrouselModel.status == True).order_by(WepCarrouselModel.id)
    else:
        # Para otros usuarios, no filtrar (devolver todo)
        query = select(WepCarrouselModel).order_by(WepCarrouselModel.id)
    return db.exec(query).all()

@router.get("/{carrousel_id}", response_model=WepCarrouselModel)
def get_carrousel(carrousel_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)):

    carrousel = db.get(WepCarrouselModel, carrousel_id)
    if not carrousel:
        raise HTTPException(status_code=404, detail="Carrousel no encontrado")
    return carrousel

@router.delete("/{carrousel_id}", status_code=204)
def delete_carrousel(carrousel_id: int, current_user: WepUserModel = Depends(verify_token),
     db: Session = Depends(get_tenant_session)):
    
    carrousel = db.get(WepCarrouselModel, carrousel_id)
    if not carrousel:
        raise HTTPException(status_code=404, detail="Carrousel no encontrado")
    
    try:
        # Eliminar imagen asociada
        FileService.delete_file(carrousel.photo, current_user.client)
        
        # Eliminar registro
        db.delete(carrousel)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando carrousel: {str(e)}"
        )