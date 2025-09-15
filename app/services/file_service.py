import uuid
from fastapi import UploadFile, HTTPException, status
from pathlib import Path
from minio import Minio
from minio.error import S3Error
from fastapi.responses import FileResponse
from ..config.config import settings
import os
from io import BytesIO

class FileService:
    _minio_client = None
    
    @staticmethod
    def get_minio_client():
        """Crea y devuelve un cliente de MinIO (singleton) solo si USE_MINIO es True"""
        if not settings.USE_MINIO:
            return None
            
        if FileService._minio_client is None:
            FileService._minio_client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE
            )
        return FileService._minio_client
    
    @staticmethod
    def validate_file(file: UploadFile):
        allowed_types = ["image/jpeg",
                         "image/png",
                         "image/webp",
                         "image/x-icon",
                         "video/mp4",
                         "video/quicktime"
                         ]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Solo se permiten imágenes o videos (MP4/MOV): {', '.join(allowed_types)}"
            )
            
    @staticmethod
    async def save_file(file: UploadFile, client_name: str) -> str:
        """Guarda archivos en MinIO o sistema local según configuración"""
        FileService.validate_file(file)
        
        # Generar nombre único
        file_ext = os.path.splitext(file.filename)[1].lower()
        filename = f"{uuid.uuid4()}{file_ext}"

        if settings.USE_MINIO:
            return await FileService._save_to_minio(file, filename, client_name)
        else:
            return await FileService._save_local(file, filename, client_name)
        
    @staticmethod
    async def _save_to_minio(file: UploadFile, filename: str, client_name: str) -> str:
        """Guarda archivo en MinIO"""
        try:
            minio_client = FileService.get_minio_client()
            if minio_client is None:
                raise HTTPException(status_code=500, detail="MinIO no configurado")

            if not minio_client.bucket_exists(settings.MINIO_BUCKET_NAME):
                minio_client.make_bucket(settings.MINIO_BUCKET_NAME)

            object_name = f"{client_name}/{filename}"
            content = await file.read()
            file_stream = BytesIO(content)
            file_size = len(content)

            minio_client.put_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=object_name,
                data=file_stream,
                length=file_size,
                content_type=file.content_type
            )
            
            return filename
            
        except S3Error as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error de MinIO: {str(e)}"
            )

    @staticmethod
    async def _save_local(file: UploadFile, filename: str, client_name: str) -> str:
        """Guarda archivo en sistema local"""
        try:
            # Crear directorio del cliente si no existe
            client_path = Path(settings.UPLOADS) / client_name
            client_path.mkdir(parents=True, exist_ok=True)
            
            file_path = client_path / filename
            
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
                
            return filename
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error al guardar archivo local: {str(e)}"
            )

    @staticmethod
    def delete_file(filename: str, client_name: str):
        """Elimina archivo según el modo de almacenamiento configurado"""
        if settings.USE_MINIO:
            FileService._delete_from_minio(filename, client_name)
        else:
            FileService._delete_local(filename, client_name)

    @staticmethod
    def _delete_from_minio(filename: str, client_name: str):
        try:
            minio_client = FileService.get_minio_client()
            if minio_client:
                object_name = f"{client_name}/{filename}"
                minio_client.remove_object(settings.MINIO_BUCKET_NAME, object_name)
        except S3Error:
            pass

    @staticmethod
    def _delete_local(filename: str, client_name: str):
        try:
            file_path = Path(settings.UPLOADS) / client_name / filename
            if file_path.exists():
                file_path.unlink()
        except:
            pass

    @staticmethod
    def get_file_url(filename: str, client_name: str, expires_seconds: int = 3600) -> str:
        """Obtiene URL del archivo según el modo configurado"""
        if settings.USE_MINIO:
            return FileService._get_minio_url(filename, client_name, expires_seconds)
        else:
            return FileService._get_local_url(filename, client_name)

    @staticmethod
    def _get_minio_url(filename: str, client_name: str, expires_seconds: int) -> str:
        try:
            minio_client = FileService.get_minio_client()
            if minio_client is None:
                raise HTTPException(status_code=500, detail="MinIO no configurado")
                
            object_name = f"{client_name}/{filename}"
            return minio_client.presigned_get_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=object_name,
                expires=expires_seconds
            )
        except S3Error as e:
            raise HTTPException(
                status_code=404,
                detail=f"Archivo no encontrado en MinIO: {str(e)}"
            )

    @staticmethod
    def _get_local_url(filename: str, client_name: str) -> str:
        file_path = Path(settings.UPLOADS) / client_name / filename
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail="Archivo local no encontrado"
            )
        return str(file_path.absolute())
    
    @staticmethod
    async def get_media(filename: str, client_name: str):
        """Devuelve el archivo según el modo configurado"""
        if settings.USE_MINIO:
            url = FileService._get_minio_url(filename, client_name, 3600)
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=url)
        else:
            file_path = FileService._get_local_url(filename, client_name)
            return FileResponse(file_path)