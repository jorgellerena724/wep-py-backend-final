from fastapi import APIRouter, Depends, Form, HTTPException, status
from typing import Optional
from sqlmodel import select, Session
from app.api.endpoints.token import get_tenant_session, verify_token
from app.models.wep_user_model import WepUserModel
from app.models.wep_contact_model import WepContactModel
import json

router = APIRouter()

# Predefinir las redes sociales básicas SIN SLUG
DEFAULT_SOCIAL_NETWORKS = [
    {"network": "whatsapp", "url": "https://wa.me/", "username": "", "active": False},
    {"network": "facebook", "url": "https://facebook.com/", "username": "", "active": False},
    {"network": "instagram", "url": "https://instagram.com/", "username": "", "active": False},
    {"network": "tiktok", "url": "https://tiktok.com/@", "username": "", "active": False},
    {"network": "x", "url": "https://x.com/", "username": "", "active": False},
    {"network": "telegram", "url": "https://t.me/", "username": "", "active": False},
]

@router.patch("/{contact_id}", response_model=WepContactModel)
async def update_contact(
    contact_id: int,
    email: Optional[str] = Form(None, max_length=100),
    address: Optional[str] = Form(None, max_length=255),
    social_networks: Optional[str] = Form(None),  # JSON string como en productos
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Obtener el contacto existente
        contact = db.get(WepContactModel, contact_id)
        if not contact:
            raise HTTPException(status_code=404, detail="Contact no encontrado")

        # Actualizar campos básicos
        if email is not None:
            contact.email = email
        
        if address is not None:
            contact.address = address
        
        # Actualizar redes sociales si se proporcionan
        if social_networks is not None:
            try:
                social_networks_data = json.loads(social_networks)
                if not isinstance(social_networks_data, list):
                    raise ValueError("social_networks debe ser una lista")
                
                # Validar cada red social
                for network in social_networks_data:
                    if not all(key in network for key in ["network", "url", "username", "active"]):
                        raise ValueError("Cada red social debe tener network, url, username y active")
                
                contact.social_networks = social_networks_data
                
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"JSON inválido: {str(e)}")
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        # Confirmar cambios
        db.commit()
        db.refresh(contact)
        
        return contact

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el contact: {str(e)}"
        )
        
@router.get("/", response_model=list[WepContactModel])
def get_contact( current_user: WepUserModel = Depends(verify_token), db: Session = Depends(get_tenant_session)):
    return db.exec(select(WepContactModel).order_by(WepContactModel.id)).all()