from fastapi import APIRouter, HTTPException, Path
from app.services.file_service import FileService

router = APIRouter()

@router.get("/{filename}")
async def get_media(filename: str):
    """
    Devuelve un archivo multimedia almacenado en el servidor.
    
    Args:
        filename: Nombre del archivo multimedia a recuperar
    """
    return await FileService.get_media(filename)