import uuid
from fastapi import UploadFile, HTTPException, status
from pathlib import Path
from minio import Minio
from minio.error import S3Error
from fastapi.responses import FileResponse, StreamingResponse, RedirectResponse
from ..config.config import settings
import os
from io import BytesIO
import mimetypes

class FileService:
    _minio_client = None
    
    @classmethod
    def _get_minio_endpoint_info(cls):
        """Información del endpoint MinIO (para debugging)"""
        if not settings.USE_MINIO:
            return "MinIO deshabilitado"
        
        return {
            "endpoint": settings.MINIO_ENDPOINT,
            "secure": settings.MINIO_SECURE,
            "bucket": settings.MINIO_BUCKET_NAME
        }
    
    @staticmethod
    def get_minio_client():
        """Crea y devuelve un cliente de MinIO (singleton) solo si USE_MINIO es True"""
        if not settings.USE_MINIO:
            return None
            
        if FileService._minio_client is None:
            try:
                # Log para debugging
                print(f"[MinIO] Conectando a: {settings.MINIO_ENDPOINT}, secure={settings.MINIO_SECURE}")
                
                FileService._minio_client = Minio(
                    endpoint=settings.MINIO_ENDPOINT,
                    access_key=settings.MINIO_ACCESS_KEY,
                    secret_key=settings.MINIO_SECRET_KEY,
                    secure=settings.MINIO_SECURE
                )
                
                # Probar conexión inmediatamente
                FileService._minio_client.list_buckets()
                print("[MinIO] Conexión exitosa")
                
            except Exception as e:
                print(f"[MinIO] Error de conexión: {e}")
                FileService._minio_client = None
                raise
                
        return FileService._minio_client
    
    @staticmethod
    def validate_file(file: UploadFile):
        allowed_types = ["image/jpeg",
                         "image/png",
                         "image/webp",
                         "image/x-icon",
                         "video/mp4",
                         "video/quicktime",
                         "application/pdf",
                         "application/zip",
                         "application/x-zip-compressed",
                         "application/octet-stream"  # Para archivos ZIP que no tienen MIME específico
                         ]
        
        # Validación especial para archivos ZIP
        file_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
        if file_ext == ".zip":
            # Si es un archivo ZIP, permitir varios tipos MIME comunes
            zip_types = ["application/zip", "application/x-zip-compressed", "application/octet-stream"]
            if file.content_type not in zip_types:
                # Si el content_type no es reconocido como ZIP, pero la extensión es .zip, permitirlo
                # Esto maneja casos donde el navegador no detecta correctamente el tipo MIME
                pass  # Permitir el archivo
        elif file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Solo se permiten imágenes, videos, PDF y archivos ZIP. Tipo recibido: {file.content_type}, archivo: {file.filename}"
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

            # Crear bucket si no existe
            if not minio_client.bucket_exists(settings.MINIO_BUCKET_NAME):
                minio_client.make_bucket(settings.MINIO_BUCKET_NAME)
                print(f"[MinIO] Bucket creado: {settings.MINIO_BUCKET_NAME}")

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
            
            print(f"[MinIO] Archivo guardado: {object_name} ({file_size} bytes)")
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
                print(f"[MinIO] Archivo eliminado: {object_name}")
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
            
            # Verificar que el objeto existe primero
            minio_client.stat_object(settings.MINIO_BUCKET_NAME, object_name)
            
            url = minio_client.presigned_get_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=object_name,
                expires=expires_seconds,
                secure=False
            )
            
            print(f"[MinIO] URL firmada generada para: {object_name}")
            return url
            
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise HTTPException(
                    status_code=404,
                    detail=f"Archivo no encontrado en MinIO: {filename}"
                )
            raise HTTPException(
                status_code=500,
                detail=f"Error MinIO al generar URL: {str(e)}"
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
    async def get_file_stream(filename: str, client_name: str) -> StreamingResponse:
        """Obtiene archivo como stream desde MinIO (proxy interno)"""
        if not settings.USE_MINIO:
            raise HTTPException(status_code=400, detail="MinIO no está habilitado")
        
        try:
            minio_client = FileService.get_minio_client()
            if minio_client is None:
                raise HTTPException(status_code=500, detail="Cliente MinIO no disponible")
            
            object_name = f"{client_name}/{filename}"
            
            # Obtener objeto como stream
            response = minio_client.get_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=object_name
            )
            
            # Obtener metadata para content-type
            try:
                stat = minio_client.stat_object(settings.MINIO_BUCKET_NAME, object_name)
                content_type = stat.content_type
            except:
                # Determinar por extensión si no se puede obtener metadata
                content_type, _ = mimetypes.guess_type(filename)
                if not content_type:
                    content_type = "application/octet-stream"
            
            # Determinar disposición del contenido
            if content_type.startswith("image/") or content_type.startswith("video/"):
                content_disposition = f'inline; filename="{filename}"'
            else:
                content_disposition = f'attachment; filename="{filename}"'
            
            print(f"[MinIO] Sirviendo archivo: {object_name} ({content_type})")
            
            return StreamingResponse(
                response,
                media_type=content_type,
                headers={
                    "Content-Disposition": content_disposition,
                    "Cache-Control": "public, max-age=86400",  # Cache 24h
                    "Access-Control-Allow-Origin": "*"  # Para CORS si es necesario
                }
            )
            
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {filename}")
            raise HTTPException(status_code=500, detail=f"Error MinIO: {str(e)}")
        finally:
            # Asegurar que se liberan recursos
            if 'response' in locals():
                try:
                    response.close()
                    response.release_conn()
                except:
                    pass
    
    @staticmethod
    async def get_media(filename: str, client_name: str, serve_directly: bool = True):
        """
        Devuelve el archivo según el modo configurado
        
        Args:
            filename: Nombre del archivo
            client_name: Nombre/Nombre del cliente
            serve_directly: True para servir directamente (proxy interno)
                           False para redirigir a URL externa (útil para debugging)
        """
        if settings.USE_MINIO:
            if serve_directly:
                # ✅ Modo interno: wep-backend sirve como proxy
                return await FileService.get_file_stream(filename, client_name)
            else:
                # ❌ Modo externo: Redirige a URL firmada (para debugging o casos especiales)
                url = FileService._get_minio_url(filename, client_name, 3600)
                return RedirectResponse(url=url)
        else:
            # Modo local
            file_path = FileService._get_local_url(filename, client_name)
            return FileResponse(file_path)

    @staticmethod
    def list_client_files(client_name: str, prefix: str = ""):
        """Lista archivos de un cliente en MinIO"""
        if not settings.USE_MINIO:
            return []
        
        try:
            minio_client = FileService.get_minio_client()
            if minio_client is None:
                return []
            
            objects = minio_client.list_objects(
                bucket_name=settings.MINIO_BUCKET_NAME,
                prefix=f"{client_name}/{prefix}",
                recursive=True
            )
            
            files = []
            for obj in objects:
                # Remover el prefijo del cliente
                filename = obj.object_name.replace(f"{client_name}/", "", 1)
                files.append({
                    "name": filename,
                    "size": obj.size,
                    "last_modified": obj.last_modified
                })
            
            return files
            
        except S3Error:
            return []