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
        """Crea y devuelve un cliente de MinIO (singleton)"""
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
        """Guarda archivos en MinIO organizados por cliente"""
        try:
            # Validar archivo
            FileService.validate_file(file)
            
            # Generar nombre único
            file_ext = os.path.splitext(file.filename)[1].lower()
            filename = f"{uuid.uuid4()}{file_ext}"
            
            # Obtener cliente MinIO
            minio_client = FileService.get_minio_client()
            
            # Asegurarse que el bucket existe
            if not minio_client.bucket_exists(settings.MINIO_BUCKET_NAME):
                minio_client.make_bucket(settings.MINIO_BUCKET_NAME)
            
            # Nombre del objeto en MinIO (cliente/nombre_archivo)
            object_name = f"{client_name}/{filename}"
            
            # Leer contenido y crear un stream de bytes
            content = await file.read()
            file_stream = BytesIO(content)
            file_size = len(content)
            
            # Subir archivo usando el stream
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
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error al guardar archivo: {str(e)}"
            )

    @staticmethod
    def delete_file(filename: str, client_name: str):
        """Elimina archivo de MinIO"""
        try:
            minio_client = FileService.get_minio_client()
            object_name = f"{client_name}/{filename}"
            minio_client.remove_object(settings.MINIO_BUCKET_NAME, object_name)
        except S3Error:
            pass  # No fallar si no se puede eliminar

    @staticmethod
    def get_file_url(filename: str, client_name: str, expires_seconds: int = 3600) -> str:
        """Devuelve una URL temporal para acceder al archivo"""
        try:
            minio_client = FileService.get_minio_client()
            object_name = f"{client_name}/{filename}"
            
            # Generar URL presigned (temporal)
            return minio_client.presigned_get_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=object_name,
                expires=expires_seconds
            )
            
        except S3Error as e:
            raise HTTPException(
                status_code=404,
                detail=f"Archivo no encontrado: {str(e)}"
            )

    @staticmethod
    async def get_media(filename: str, client_name: str):
        """Devuelve el archivo solicitado (imagen o video)"""
        try:
            url = FileService.get_file_url(filename, client_name)
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=url)
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al recuperar imagen: {str(e)}"
            )