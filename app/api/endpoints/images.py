from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from app.api.endpoints.token import verify_token
from app.models.wep_user_model import WepUserModel
from app.services.file_service import FileService
import mimetypes

router = APIRouter()

@router.get("/{filename}/")
async def get_media(
    filename: str, 
    current_user: WepUserModel = Depends(verify_token),
    direct: bool = Query(
        True, 
        description="True: sirve archivo directamente (proxy interno). False: redirige a URL externa"
    )
):
    """
    Devuelve un archivo multimedia almacenado en MinIO o localmente.
    
    Args:
        filename: Nombre del archivo multimedia a recuperar
        direct: Si True, wep-backend sirve como proxy. Si False, redirige a URL externa.
    """
    try:
        return await FileService.get_media(filename, current_user.client, serve_directly=direct)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al obtener archivo: {str(e)}"
        )

@router.get("/{client_id}/{filename}")
async def get_client_media(
    client_id: str = Path(..., description="ID del cliente"),
    filename: str = Path(..., description="Nombre del archivo"),
    current_user: WepUserModel = Depends(verify_token),
    direct: bool = Query(True, description="Sirve directamente como proxy")
):
    """
    Obtiene archivo multimedia de un cliente específico.
    Valida que el usuario actual tenga acceso a este cliente.
    """
    # Validar que el usuario tiene acceso a este cliente
    if str(current_user.client) != client_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="No tienes acceso a los archivos de este cliente"
        )
    
    try:
        return await FileService.get_media(filename, client_id, serve_directly=direct)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al obtener archivo: {str(e)}"
        )

# Endpoint para debugging/verificación (sin autenticación en desarrollo)
@router.get("/health/minio")
async def check_minio_health():
    """
    Verifica la conexión con MinIO (solo para debugging)
    """
    try:
        # Intenta crear cliente y listar buckets
        client = FileService.get_minio_client()
        if not client:
            return {"status": "disabled", "use_minio": False}
        
        buckets = client.list_buckets()
        bucket_names = [b.name for b in buckets]
        
        return {
            "status": "connected",
            "buckets": bucket_names,
            "endpoint": FileService._get_minio_endpoint_info()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "endpoint": FileService._get_minio_endpoint_info()
        }