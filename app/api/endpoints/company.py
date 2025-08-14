from fastapi import APIRouter, File, UploadFile, Form, Depends, HTTPException, status
from typing import Optional
from sqlmodel import select, Session
from app.api.endpoints.token import get_tenant_session, verify_token
from app.models.wep_user_model import WepUserModel
from app.models.wep_company_model import WepCompanyModel
from app.services.file_service import FileService

router = APIRouter()

@router.post("/", response_model=WepCompanyModel)
async def create_company(
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
        company = WepCompanyModel(title=title, description=description, photo=photo_filename)
        db.add(company)
        db.commit()
        db.refresh(company)
        return company
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creando company: {str(e)}"
        )


@router.patch("/{company_id}", response_model=WepCompanyModel)
async def update_company(
    company_id: int,
    title: Optional[str] = Form(None, max_length=100), 
    description: Optional[str] = Form(None),           
    photo: Optional[UploadFile] = File(None),          
    status: Optional[bool] = Form(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        company = db.get(WepCompanyModel, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company no encontrado")

        # Actualizar solo los campos proporcionados
        if title is not None:
            company.title = title
        if description is not None:
            company.description = description
        if status is not None:
            company.status = status

        # Manejo de imagen (opcional)
        if photo is not None:
            FileService.validate_file(photo)
            if company.photo:
                FileService.delete_file(company.photo, current_user.client)
            company.photo = await FileService.save_file(photo, current_user.client)

        db.commit()
        db.refresh(company)
        return company

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al actualizar el Company: {str(e)}"
        )
    
@router.get("/", response_model=list[WepCompanyModel])
def get_companyl( current_user: WepUserModel = Depends(verify_token),db: Session = Depends(get_tenant_session)):
   
    source = getattr(current_user, 'source', 'unknown')
    
    if source == "website":
        query = select(WepCompanyModel).where(WepCompanyModel.status == True).order_by(WepCompanyModel.id)
    else:
    # Para otros usuarios, no filtrar (devolver todo)
        query = select(WepCompanyModel).order_by(WepCompanyModel.id)
    
    company = db.exec(query).all()
    return company
   
   

@router.get("/{company_id}", response_model=WepCompanyModel)
def get_company(company_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)):

    company = db.get(WepCompanyModel, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company no encontrado")
    return company

@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, current_user: WepUserModel = Depends(verify_token),
     db: Session = Depends(get_tenant_session)):
    
    company = db.get(WepCompanyModel,company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company no encontrado")
    
    try:
        # Eliminar imagen asociada
        FileService.delete_file(company.photo, current_user.client)
        
        # Eliminar registro
        db.delete(company)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando company: {str(e)}"
        )