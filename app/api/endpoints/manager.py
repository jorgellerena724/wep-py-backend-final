from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, status
from typing import Optional
from sqlmodel import select, Session
from app.api.endpoints.token import verify_token, get_tenant_session
from app.models.wep_user_model import WepUserModel
from app.models.wep_manager_model import WepManagerModel
from app.services.file_service import FileService

router = APIRouter()

@router.post("/", response_model=WepManagerModel)
async def create_manager(
    title: str = Form(..., max_length=100),
    description: str = Form(...),
    charge: str = Form(...,max_length=100),
    photo: Optional[UploadFile] = Form(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    # Validar imagen
    if photo:
        FileService.validate_file(photo)
    
    try:
        # Guardar imagen (solo nombre)
        photo_filename = None
        if photo:
            photo_filename = await FileService.save_file(photo, current_user.client)
        
        # Crear registro
        manager = WepManagerModel(title=title, description=description,charge=charge, photo=photo_filename)
        db.add(manager)
        db.commit()
        db.refresh(manager)
        return manager
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creando manager: {str(e)}"
        )


@router.patch("/{manager_id}", response_model=WepManagerModel)
async def update_manager(
    manager_id: int,
    title: Optional[str] = Form(..., max_length=100),
    description: Optional[str] = Form(...),
    charge: Optional[str]= Form(...,max_length=100),
    photo: Optional[UploadFile] = Form(None),
    remove_photo: Optional[bool] = Form(False),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Obtener el header existente
        manager = db.get(WepManagerModel, manager_id)
        if not manager:
            raise HTTPException(status_code=404, detail="Manager no encontrado")

        # Actualizar nombre si se proporciona
        if title is not None:
            manager.title = title

        # Actualizar description si se proporciona
        if description is not None:
            manager.description = description

        # Actualizar charge si se proporciona
        if charge is not None:
            manager.charge = charge

        # Procesar imagen si se proporciona
        if remove_photo:
            if manager.photo:
                FileService.delete_file(manager.photo, current_user.client)
                manager.photo = None

        # Manejo de nueva foto
        if photo is not None and photo.filename:  # Verificar que es un archivo válido
            FileService.validate_file(photo)
            if manager.photo:
                FileService.delete_file(manager.photo, current_user.client)
            new_filename = await FileService.save_file(photo, current_user.client)
            manager.photo = new_filename

        # Confirmar cambios en la base de datos
        db.commit()
        db.refresh(manager)
        
        return manager

    except HTTPException:
        # Re-lanzar excepciones HTTP que ya estamos manejando
        db.rollback()
        raise

    except Exception as e:
        # Revertir cambios en caso de cualquier otro error
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el manager: {str(e)}"
        )

@router.get("/", response_model=list[WepManagerModel])
def get_manager( current_user: WepUserModel = Depends(verify_token),db: Session = Depends(get_tenant_session)):
    return db.exec(select(WepManagerModel).order_by(WepManagerModel.id)).all()

@router.get("/{manager_id}", response_model=WepManagerModel)
def get_manager(manager_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)):

    manager = db.get(WepManagerModel, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Manager no encontrado")
    return manager

@router.delete("/{manager_id}", status_code=204)
def delete_manager(manager_id: int, current_user: WepUserModel = Depends(verify_token),
     db: Session = Depends(get_tenant_session)):
    
    manager = db.get(WepManagerModel, manager_id)
    if not manager:
        raise HTTPException(status_code=404, detail="Manager no encontrado")
    
    try:
        # Eliminar imagen asociada
        FileService.delete_file(manager.photo, current_user.client)
        
        # Eliminar registro
        db.delete(manager)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando manager: {str(e)}"
        )