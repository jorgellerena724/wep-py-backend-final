from fastapi import APIRouter, Depends, HTTPException, Path, Query, UploadFile, File, Form
from fastapi.responses import JSONResponse
from app.api.endpoints.token import verify_token
from app.models.wep_user_model import WepUserModel
from app.services.file_service import FileService
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    current_user: WepUserModel = Depends(verify_token),
    optimize: bool = Form(True, description="Optimizar archivo para web"),
    keep_original: bool = Form(False, description="Guardar también versión original")
):
    """
    Sube un archivo multimedia (imagen/video)
    
    Devuelve:
    - filename: Nombre COMPLETO del archivo guardado (para guardar en BD)
    - original_name: Nombre original del archivo
    - optimized: Si fue optimizado
    - content_type: Tipo MIME final
    - format: Extensión sin punto (ej: 'webp', 'mp4', 'jpg')
    - size: Tamaño en bytes
    """
    try:
        logger.info(f"Subiendo archivo: {file.filename} para usuario: {current_user.username}")
        
        result = await FileService.save_file(
            file=file,
            client_name=current_user.client,
            optimize=optimize,
            keep_original=keep_original
        )
        
        # Log exitoso
        logger.info(f"Archivo subido exitosamente: {result['filename']}")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": result.get("message", "Archivo guardado exitosamente"),
                "data": {
                    "filename": result["filename"],  # ⬅️ ESTO es lo que guardas en BD
                    "original_name": result["original_name"],
                    "optimized": result["optimized"],
                    "content_type": result["content_type"],
                    "format": result["format"],
                    "size": result["size"],
                    "url": f"/api/images/{result['filename']}/",
                    "download_url": f"/api/images/{current_user.client}/{result['filename']}"
                }
            }
        )
        
    except HTTPException as e:
        logger.error(f"Error HTTP al subir archivo: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Error interno al subir archivo: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al procesar archivo: {str(e)}"
        )

@router.get("/{filename}/")
async def get_media(
    filename: str, 
    current_user: WepUserModel = Depends(verify_token)
):
    """
    Devuelve un archivo multimedia almacenado localmente.
    
    Args:
        filename: Nombre COMPLETO del archivo (ej: '3d3f8980-e507-408b-94bd-70031904d306.webp')
    """
    try:
        return await FileService.get_media(filename, current_user.client)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error obteniendo archivo {filename}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al obtener archivo: {str(e)}"
        )

@router.get("/{client_id}/{filename}")
async def get_client_media(
    client_id: str = Path(..., description="ID del cliente"),
    filename: str = Path(..., description="Nombre COMPLETO del archivo"),
    current_user: WepUserModel = Depends(verify_token)
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
        return await FileService.get_media(filename, client_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error obteniendo archivo {filename}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al obtener archivo: {str(e)}"
        )

@router.delete("/{filename}")
async def delete_media(
    filename: str,
    current_user: WepUserModel = Depends(verify_token)
):
    """
    Elimina un archivo multimedia
    """
    try:
        FileService.delete_file(filename, current_user.client)
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": f"Archivo {filename} eliminado exitosamente"
            }
        )
    except Exception as e:
        logger.error(f"Error eliminando archivo {filename}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al eliminar archivo: {str(e)}"
        )

@router.get("/list/")
async def list_media(
    current_user: WepUserModel = Depends(verify_token),
    prefix: str = Query("", description="Prefijo para filtrar archivos")
):
    """
    Lista todos los archivos del cliente actual
    """
    try:
        files = FileService.list_client_files(current_user.client, prefix)
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "count": len(files),
                "data": files
            }
        )
    except Exception as e:
        logger.error(f"Error listando archivos: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al listar archivos: {str(e)}"
        )

# Endpoint para verificación
@router.get("/health/local")
async def check_local_storage():
    """
    Verifica el estado del almacenamiento local
    """
    try:
        from app.config import settings
        uploads_path = Path(settings.UPLOADS)
        exists = uploads_path.exists()
        is_dir = uploads_path.is_dir() if exists else False
        
        return {
            "status": "ok" if exists and is_dir else "warning",
            "exists": exists,
            "is_directory": is_dir,
            "path": str(uploads_path.absolute()),
            "free_space_gb": uploads_path.stat().st_size / (1024**3) if exists else 0
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }