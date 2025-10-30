from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, status
from typing import Optional
from sqlmodel import select, Session
from app.api.endpoints.token import get_tenant_session, verify_token
from app.models.wep_header_model import WepHeaderModel
from app.models.wep_user_model import WepUserModel
from app.services.file_service import FileService

router = APIRouter()

@router.post("/", response_model=WepHeaderModel)
async def create_header(
    name: str = Form(...),
    photo: UploadFile = Form(...),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    # Validar imagen
    FileService.validate_file(photo)
    
    try:
        # Guardar imagen (solo nombre)
        logo_filename = await FileService.save_file(photo, current_user.client)
        
        # Crear registro
        header = WepHeaderModel(name=name, logo=logo_filename)
        db.add(header)
        db.commit()
        db.merge(header)
        return header
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creando header: {str(e)}"
        )

from sqlalchemy import exc
from fastapi import status

@router.patch("/{header_id}", response_model=WepHeaderModel)
async def update_header(
    header_id: int,
    name: Optional[str] = Form(None),
    photo: Optional[UploadFile] = Form(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Obtener el header existente
        header = db.get(WepHeaderModel, header_id)
        if not header:
            raise HTTPException(status_code=404, detail="Header no encontrado")

        # Actualizar nombre si se proporciona
        if name is not None:
            header.name = name

        # Procesar imagen si se proporciona
        if photo is not None:
            # Validar tipo de imagen
            FileService.validate_file(photo)
            
            # Eliminar imagen anterior si existe
            if header.logo:
                FileService.delete_file(header.logo, current_user.client)
            
            # Guardar nueva imagen
            new_filename = await FileService.save_file(photo, current_user.client)
            header.logo = new_filename

        # Confirmar cambios en la base de datos
        db.commit()
        db.merge(header)
        
        return header

    except HTTPException:
        # Re-lanzar excepciones HTTP que ya estamos manejando
        db.rollback()
        raise

    except Exception as e:
        # Revertir cambios en caso de cualquier otro error
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el header: {str(e)}"
        )

@router.get("/", response_model=list[WepHeaderModel])
def get_headers( current_user: WepUserModel = Depends(verify_token),db: Session = Depends(get_tenant_session)):
    return db.exec(select(WepHeaderModel).order_by(WepHeaderModel.id)).all()

@router.get("/{header_id}", response_model=WepHeaderModel)
def get_header(header_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)):

    header = db.get(WepHeaderModel, header_id)
    if not header:
        raise HTTPException(status_code=404, detail="Header no encontrado")
    return header

@router.delete("/{header_id}", status_code=204)
def delete_header(header_id: int, current_user: WepUserModel = Depends(verify_token),
     db: Session = Depends(get_tenant_session)):
    
    header = db.get(WepHeaderModel, header_id)
    if not header:
        raise HTTPException(status_code=404, detail="Header no encontrado")
    
    try:
        # Eliminar imagen asociada
        FileService.delete_file(header.logo, current_user.client)
        
        # Eliminar registro
        db.delete(header)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando header: {str(e)}"
        )