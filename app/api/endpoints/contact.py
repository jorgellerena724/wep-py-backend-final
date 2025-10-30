from fastapi import APIRouter, Form, Depends, HTTPException, status
from typing import Optional
from sqlmodel import select
from app.api.endpoints.token import get_tenant_session, verify_token
from app.models.wep_user_model import WepUserModel
from app.models.wep_contact_model import WepContactModel
from sqlalchemy.orm import Session

router = APIRouter()

@router.post("/", response_model=WepContactModel)
async def create_contact(
    email: str = Form(..., max_length=100),
    phone: str = Form(..., max_length=100),
    address: str = Form(..., max_length=255),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Crear registro
        contact = WepContactModel(email=email, phone=phone, address=address)
        db.add(contact)
        db.commit()
        db.merge(contact)
        return contact
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creando contact: {str(e)}"
        )


@router.patch("/{contact_id}", response_model=WepContactModel)
async def update_contact(
    contact_id: int,
    email: Optional[str] = Form(..., max_length=100),
    phone: Optional[str] = Form(..., max_length=100),
    address: Optional[str] = Form(None, max_length=255),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Obtener el header existente
        contact = db.get(WepContactModel, contact_id)
        if not contact:
            raise HTTPException(status_code=404, detail="Contact no encontrado")

       
        if email is not None:
            contact.email = email

        if phone is not None:
            contact.phone = phone
        
        if address is not None:
            contact.address = address

        # Confirmar cambios en la base de datos
        db.commit()
        db.merge(contact)
        
        return contact

    except HTTPException:
        # Re-lanzar excepciones HTTP que ya estamos manejando
        db.rollback()
        raise

    except Exception as e:
        # Revertir cambios en caso de cualquier otro error
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el contact: {str(e)}"
        )

@router.get("/", response_model=list[WepContactModel])
def get_contact( current_user: WepUserModel = Depends(verify_token),db: Session = Depends(get_tenant_session)):
    return db.exec(select(WepContactModel).order_by(WepContactModel.id)).all()

@router.get("/{contact_id}", response_model=WepContactModel)
def get_contact(contact_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)):

    contact = db.get(WepContactModel, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact no encontrado")
    return contact

@router.delete("/{contact_id}", status_code=204)
def delete_contact(contact_id: int, current_user: WepUserModel = Depends(verify_token),
     db: Session = Depends(get_tenant_session)):
    
    contact = db.get(WepContactModel, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact no encontrado")
    
    try:
       
        # Eliminar registro
        db.delete(contact)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando contact: {str(e)}"
        )