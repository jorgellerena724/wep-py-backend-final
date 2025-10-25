from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException
from typing import Optional
from sqlmodel import SQLModel, select, Session
from app.api.endpoints.token import get_tenant_session, verify_token
from app.models.wep_user_model import WepUserModel
from app.models import WepPublicationModel
from app.services.file_service import FileService
from sqlalchemy.orm import selectinload

class CategoryRead(SQLModel):
    id: int
    title: str

class PublicationRead(SQLModel):
    id: int
    title: str
    publication_category: CategoryRead
    photo: str | None
    file: str

router = APIRouter()

@router.post("/", response_model=WepPublicationModel)
async def create_publication(
    title: str = Form(..., max_length=100),
    publication_category_id: int = Form(...),
    photo: Optional[UploadFile] = None,  # ✅ Usar Optional
    file: UploadFile = Form(...),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    # Validar que file sea obligatorio
    if file is None:
        raise HTTPException(status_code=400, detail="El archivo es obligatorio")
   
    # Validar archivo obligatorio
    FileService.validate_file(file)
    
    # Validar imagen solo si existe
    if photo is not None:
        FileService.validate_file(photo)
   
    try:
        # Guardar archivo obligatorio
        file_filename = await FileService.save_file(file, current_user.client)
        
        # ✅ Guardar imagen solo si existe
        photo_filename = None
        if photo is not None:
            photo_filename = await FileService.save_file(photo, current_user.client)
       
        # Crear registro
        publication = WepPublicationModel(
            title=title, 
            file=file_filename,
            publication_category_id=publication_category_id,
            photo=photo_filename  # Puede ser None
        )
        db.add(publication)
        db.commit()
        db.merge(publication)
        return publication
       
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creando publication: {str(e)}"
        )

@router.patch("/{publication_id}", response_model=WepPublicationModel)
async def update_publication(
    publication_id: int,
    title: Optional[str] = Form(None, max_length=100),
    file: Optional[UploadFile] = Form(None),
    publication_category_id: Optional[int] = Form(None),
    photo: Optional[UploadFile] = Form(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Obtener el header existente
        publication = db.get(WepPublicationModel, publication_id)
        if not publication:
            raise HTTPException(status_code=404, detail="Publicación no encontrado")

        # Actualizar nombre si se proporciona
        if title is not None:
            publication.title = title
            
        if publication_category_id is not None:
            publication.publication_category_id = publication_category_id

         # Actualizar descripcion si se proporciona
        if file is not None:
            # Validar tipo de imagen
            FileService.validate_file(file)
            
            # Eliminar imagen anterior si existe
            if publication.file:
                FileService.delete_file(publication.file, current_user.client)
            
            # Guardar nueva imagen
            new_filename = await FileService.save_file(file, current_user.client)
            publication.file = new_filename

        # Procesar imagen si se proporciona
        if photo is not None:
            # Validar tipo de imagen
            FileService.validate_file(photo)
            
            # Eliminar imagen anterior si existe
            if publication.photo:
                FileService.delete_file(publication.photo, current_user.client)
            
            # Guardar nueva imagen
            new_filename = await FileService.save_file(photo, current_user.client)
            publication.photo = new_filename

        # Confirmar cambios en la base de datos
        db.commit()
        db.merge(publication)
        
        return publication

    except HTTPException:
        # Re-lanzar excepciones HTTP que ya estamos manejando
        db.rollback()
        raise

    except Exception as e:
        # Revertir cambios en caso de cualquier otro error
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al actualizar el publication: {str(e)}"
        )

@router.get("/", response_model=list[PublicationRead])
def get_publication( current_user: WepUserModel = Depends(verify_token),db: Session = Depends(get_tenant_session)):
    
    query = select(WepPublicationModel).options(selectinload(WepPublicationModel.publication_category)).order_by(WepPublicationModel.id)
    
    pbl = db.exec(query).all()
    return [PublicationRead.model_validate(p) for p in pbl]

@router.get("/{publication_id}", response_model=WepPublicationModel)
def get_publication(publication_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)):

    publication = db.get(PublicationRead, publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Carrousel no encontrado")
    return publication

@router.delete("/{publication_id}", status_code=204)
def delete_publication(publication_id: int, current_user: WepUserModel = Depends(verify_token),
     db: Session = Depends(get_tenant_session)):
    
    publication = db.get(WepPublicationModel, publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="Publicación no encontrada")
    
    try:
        # Eliminar imagen asociada
        FileService.delete_file(publication.photo, current_user.client)
        FileService.delete_file(publication.file, current_user.client)
        
        # Eliminar registro
        db.delete(publication)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando publication: {str(e)}"
        )