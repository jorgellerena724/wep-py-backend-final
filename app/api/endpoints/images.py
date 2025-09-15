from fastapi import APIRouter, Depends, HTTPException, Path
from app.api.endpoints.token import verify_token
from app.models.wep_user_model import WepUserModel
from app.services.file_service import FileService

router = APIRouter()

@router.get("/{filename}")
async def get_media(filename: str, current_user: WepUserModel = Depends(verify_token)):
    """
    Devuelve un archivo multimedia almacenado en el servidor.
    
    Args:
        filename: Nombre del archivo multimedia a recuperar
    """
    return await FileService.get_media(filename, current_user.client)