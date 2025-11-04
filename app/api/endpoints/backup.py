from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, BackgroundTasks
from fastapi.responses import FileResponse
from app.api.endpoints.token import verify_token
from app.models.wep_user_model import WepUserModel
from app.config.config import settings
from pathlib import Path
import zipfile
import shutil
import tempfile
import logging
import os

router = APIRouter()
logger = logging.getLogger(__name__)


def cleanup_temp_file(file_path: str):
    """Función para limpiar archivos temporales después de enviar"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"✅ Archivo temporal eliminado: {file_path}")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo eliminar archivo temporal {file_path}: {e}")

@router.get("/backup/download")
async def download_backup(
    background_tasks: BackgroundTasks,
    current_user: WepUserModel = Depends(verify_token)
):
    """
    Crea un backup de la base de datos SQLite y la carpeta uploads en un archivo ZIP.
    Solo funciona cuando USE_SQLITE=True.
    """
    if not settings.USE_SQLITE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El backup solo está disponible cuando USE_SQLITE=True"
        )
    
    try:
        # Obtener rutas
        db_path = Path(settings.SQLITE_DB_PATH)
        uploads_path = Path(settings.UPLOADS)
        
        # Verificar que la BD existe
        if not db_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Base de datos no encontrada en: {db_path}"
            )
        
        # Crear archivo temporal para el ZIP
        temp_dir = tempfile.mkdtemp()
        backup_filename = f"backup_{current_user.client}_{Path(db_path).stem}.zip"
        backup_path = Path(temp_dir) / backup_filename
        
        try:
            # Crear el archivo ZIP
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Agregar la base de datos
                if db_path.exists():
                    zipf.write(db_path, db_path.name)
                    logger.info(f"✅ Base de datos agregada al backup: {db_path.name}")
                
                # Agregar la carpeta uploads completa
                if uploads_path.exists() and uploads_path.is_dir():
                    for root, dirs, files in os.walk(uploads_path):
                        # Evitar archivos temporales y ocultos
                        dirs[:] = [d for d in dirs if not d.startswith('.')]
                        
                        for file in files:
                            if not file.startswith('.'):
                                file_path = Path(root) / file
                                # Mantener la estructura relativa dentro del zip (preservar carpeta uploads)
                                arcname = Path('uploads') / file_path.relative_to(uploads_path)
                                zipf.write(file_path, str(arcname))
                    logger.info(f"✅ Carpeta uploads agregada al backup: {uploads_path}")
                else:
                    logger.warning(f"⚠️ Carpeta uploads no encontrada: {uploads_path}")
            
            # Agregar tarea de limpieza después de enviar
            background_tasks.add_task(cleanup_temp_file, str(backup_path))
            
            # Retornar el archivo ZIP como respuesta
            return FileResponse(
                path=str(backup_path),
                filename=backup_filename,
                media_type='application/zip'
            )
            
        except Exception as e:
            # Limpiar archivo temporal en caso de error
            if backup_path.exists():
                backup_path.unlink()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al crear el backup: {str(e)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error inesperado al crear backup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error inesperado: {str(e)}"
        )


@router.post("/backup/restore")
async def restore_backup(
    file: UploadFile = File(...),
    current_user: WepUserModel = Depends(verify_token)
):
    """
    Restaura un backup desde un archivo ZIP.
    Sobreescribe la base de datos SQLite y la carpeta uploads.
    Solo funciona cuando USE_SQLITE=True.
    """
    if not settings.USE_SQLITE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La restauración solo está disponible cuando USE_SQLITE=True"
        )
    
    # Verificar que el archivo es un ZIP
    if not file.filename.endswith('.zip'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe ser un archivo ZIP (.zip)"
        )
    
    temp_dir = None
    try:
        # Crear directorio temporal
        temp_dir = tempfile.mkdtemp()
        zip_path = Path(temp_dir) / file.filename
        
        # Guardar el archivo subido
        with open(zip_path, 'wb') as f:
            content = await file.read()
            f.write(content)
        
        # Obtener rutas
        db_path = Path(settings.SQLITE_DB_PATH)
        uploads_path = Path(settings.UPLOADS)
        
        # Extraer el ZIP
        extract_dir = Path(temp_dir) / "extracted"
        extract_dir.mkdir()
        
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(extract_dir)
        
        # Buscar la base de datos en el ZIP extraído
        db_found = False
        db_backup_path = None
        
        # Buscar archivos .db o .sqlite en el directorio extraído
        for db_file in extract_dir.rglob('*.db'):
            db_backup_path = db_file
            db_found = True
            break
        
        if not db_found:
            for db_file in extract_dir.rglob('*.sqlite'):
                db_backup_path = db_file
                db_found = True
                break
        
        if not db_found:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se encontró un archivo de base de datos (.db o .sqlite) en el backup"
            )
        
        # Hacer backup de la BD actual antes de sobreescribir
        if db_path.exists():
            backup_current_db = db_path.with_suffix(f'.db.backup_{Path(db_path).stem}')
            shutil.copy2(db_path, backup_current_db)
            logger.info(f"✅ Backup de BD actual creado: {backup_current_db}")
        
        # Restaurar la base de datos
        shutil.copy2(db_backup_path, db_path)
        logger.info(f"✅ Base de datos restaurada desde: {db_backup_path.name}")
        
        # Restaurar la carpeta uploads
        uploads_backup_path = None
        
        # Buscar la carpeta uploads en el ZIP extraído
        # Puede estar en la raíz o en algún subdirectorio
        for possible_uploads in extract_dir.rglob('uploads'):
            if possible_uploads.is_dir():
                uploads_backup_path = possible_uploads
                break
        
        # Si no encontramos una carpeta uploads, buscar en la raíz del extract_dir
        if not uploads_backup_path:
            possible_path = extract_dir / 'uploads'
            if possible_path.exists() and possible_path.is_dir():
                uploads_backup_path = possible_path
        
        if uploads_backup_path and uploads_backup_path.exists():
            # Hacer backup de uploads actual si existe
            if uploads_path.exists():
                backup_current_uploads = uploads_path.parent / f"{uploads_path.name}_backup"
                if backup_current_uploads.exists():
                    shutil.rmtree(backup_current_uploads)
                shutil.copytree(uploads_path, backup_current_uploads)
                logger.info(f"✅ Backup de uploads actual creado: {backup_current_uploads}")
            
            # Eliminar uploads actual
            if uploads_path.exists():
                shutil.rmtree(uploads_path)
            
            # Restaurar uploads desde el backup
            shutil.copytree(uploads_backup_path, uploads_path)
            logger.info(f"✅ Carpeta uploads restaurada desde: {uploads_backup_path.name}")
        else:
            logger.warning("⚠️ No se encontró carpeta uploads en el backup, se mantiene la actual")
        
        return {
            "message": "Backup restaurado exitosamente",
            "database_restored": True,
            "uploads_restored": uploads_backup_path is not None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error al restaurar backup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al restaurar el backup: {str(e)}"
        )
    finally:
        # Limpiar archivos temporales
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir)

