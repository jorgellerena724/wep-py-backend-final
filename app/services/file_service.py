import uuid
from fastapi import UploadFile, HTTPException
from pathlib import Path
import os
from io import BytesIO
import mimetypes
from fastapi.responses import FileResponse
from PIL import Image
from pillow_heif import register_heif_opener
import subprocess
import tempfile
from typing import Tuple, Dict
import logging

from ..config.config import settings

# Configurar logging
logger = logging.getLogger(__name__)

# Registrar opener para HEIF/AVIF al inicio del módulo
register_heif_opener()

class FileOptimizer:
    """Clase para optimizar imágenes y videos para web"""
    
    @staticmethod
    def should_optimize(content_type: str, filename: str) -> bool:
        """Determina si un archivo debe ser optimizado"""
        optimizable_image_types = [
            "image/jpeg", "image/png", "image/gif", "image/bmp", "image/tiff",
            "image/heif", "image/heic", "image/avif"
        ]
        optimizable_video_types = [
            "video/mp4", "video/avi", "video/mov", "video/wmv", "video/flv", 
            "video/quicktime", "video/x-msvideo", "video/x-matroska", "video/3gpp",
            "video/x-ms-wmv", "video/x-flv", "video/webm"
        ]
        
        # Verificar por extensión también
        file_ext = Path(filename).suffix.lower()
        
        # No optimizar si ya está en formato óptimo para IMÁGENES
        if (content_type == "image/webp" or file_ext == '.webp' or
            file_ext == '.avif'):
            return False
        
        # Incluir por extensión si el content_type no es reconocido
        if file_ext in ['.avif', '.heif', '.heic', '.jpeg', '.jpg', '.png', '.gif', '.bmp', '.tiff', '.tif']:
            return True
        
        # Para video, también verificar por extensión común
        video_extensions = ['.mov', '.avi', '.wmv', '.flv', '.mkv', '.webm', '.mp4', '.m4v', '.3gp', '.mpeg', '.mpg']
        if file_ext in video_extensions:
            return True
        
        return content_type in optimizable_image_types + optimizable_video_types
    
    @staticmethod
    async def optimize_image(
        file_content: bytes,
        original_filename: str,
        max_width: int = 1920,
        quality: int = 75
    ) -> Tuple[bytes, str, str]:
        """
        Optimiza imagen para web con soporte para HEIF/AVIF
        Retorna: (contenido_optimizado, nuevo_nombre_completo, nuevo_content_type)
        """
        try:
            # Abrir imagen desde bytes (pillow-heif ya registrado maneja AVIF/HEIF)
            image = Image.open(BytesIO(file_content))
            
            # Log del formato original detectado
            logger.info(f"Optimizando imagen: {original_filename}, formato: {image.format}, modo: {image.mode}")
            
            # Convertir a RGB si es necesario (para PNG con transparencia)
            has_alpha = image.mode in ('RGBA', 'LA', 'P')
            
            if has_alpha:
                # Si tiene transparencia, mantener formato PNG
                if image.mode == 'P':
                    image = image.convert('RGBA')
                
                # Para PNG con transparencia, mantener como PNG optimizado
                output_buffer = BytesIO()
                image.save(output_buffer, format='PNG', optimize=True)
                new_filename = f"{Path(original_filename).stem}.png"
                new_content_type = "image/png"
                logger.info(f"Imagen con transparencia mantenida como PNG: {new_filename}")
                return output_buffer.getvalue(), new_filename, new_content_type
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Redimensionar si es muy grande
            original_size = (image.width, image.height)
            if image.width > max_width:
                ratio = max_width / image.width
                new_height = int(image.height * ratio)
                image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"Imagen redimensionada: {original_size} -> {image.size}")
            
            # Siempre convertir a WebP para mejor compresión web (excepto PNG con transparencia)
            output_buffer = BytesIO()
            image.save(output_buffer, format='WEBP', quality=quality, method=6)
            new_filename = f"{Path(original_filename).stem}.webp"
            new_content_type = "image/webp"
            
            logger.info(f"Imagen convertida a WebP: {original_filename} -> {new_filename}")
            
            return output_buffer.getvalue(), new_filename, new_content_type
            
        except Exception as e:
            logger.error(f"Error optimizando imagen {original_filename}: {e}")
            # Si falla, devolver el original
            return file_content, original_filename, "image/jpeg"
    
    @staticmethod
    async def optimize_video(
        file_content: bytes,
        original_filename: str,
        max_width: int = 1280,
        crf: int = 24
    ) -> Tuple[bytes, str, str]:
        """
        Optimiza video para web usando FFmpeg
        Retorna: (contenido_optimizado, nuevo_nombre_completo, nuevo_content_type)
        """
        input_path = None
        output_path = None
        
        try:
            # Crear archivos temporales
            original_ext = Path(original_filename).suffix
            with tempfile.NamedTemporaryFile(suffix=original_ext, delete=False) as input_file:
                input_file.write(file_content)
                input_path = input_file.name
            
            # Nombre de salida con extensión .mp4
            output_filename = f"{Path(original_filename).stem}.mp4"
            output_path = os.path.join(tempfile.gettempdir(), f"optimized_{uuid.uuid4()}.mp4")
            
            logger.info(f"Optimizando video: {original_filename} -> {output_filename}")
            
            # Comando FFmpeg para optimizar
            # H.264 codec, optimizado para web streaming
            command = [
                'ffmpeg',
                '-i', input_path,  # Archivo de entrada
                '-c:v', 'libx264',  # Codec de video H.264
                '-preset', 'slow',  # Balance entre velocidad y compresión
                '-crf', str(crf),  # Calidad (18-28, menor = mejor calidad)
                '-vf', f'scale=min({max_width}\,iw):-2',  # Redimensionar manteniendo ratio
                '-c:a', 'aac',  # Audio codec
                '-b:a', '128k',  # Bitrate audio
                '-movflags', '+faststart',  # Para streaming rápido (metadata al inicio)
                '-y',  # Sobrescribir si existe
                output_path
            ]
            
            # Ejecutar FFmpeg
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                # Si falla FFmpeg, devolver original
                return file_content, original_filename, "video/mp4"
            
            # Leer archivo optimizado
            with open(output_path, 'rb') as f:
                optimized_content = f.read()
            
            original_size = len(file_content)
            optimized_size = len(optimized_content)
            savings = ((original_size - optimized_size) / original_size * 100) if original_size > 0 else 0
            
            logger.info(f"Video optimizado: {original_filename} -> {output_filename} "
                       f"({optimized_size/1024/1024:.2f} MB, ahorro: {savings:.1f}%)")
            
            return optimized_content, output_filename, "video/mp4"
            
        except Exception as e:
            logger.error(f"Error optimizando video {original_filename}: {e}")
            # Si falla, devolver el original
            return file_content, original_filename, "video/mp4"
        finally:
            # Limpieza segura de archivos temporales
            for path in [input_path, output_path]:
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception as e:
                        logger.warning(f"No se pudo eliminar archivo temporal {path}: {e}")
    
    @staticmethod
    async def optimize_file(
        file: UploadFile,
        optimize: bool = True
    ) -> Tuple[bytes, str, str]:
        """
        Optimiza archivo automáticamente según su tipo
        Retorna: (contenido, nombre_completo, content_type)
        """
        content = await file.read()
        
        if not optimize:
            return content, file.filename, file.content_type
        
        if file.content_type.startswith('image/'):
            return await FileOptimizer.optimize_image(
                content, 
                file.filename
            )
        elif file.content_type.startswith('video/'):
            return await FileOptimizer.optimize_video(
                content,
                file.filename
            )
        else:
            # Para otros tipos, devolver sin cambios
            return content, file.filename, file.content_type


class FileService:
    """Servicio de archivos con optimización automática"""
    
    @staticmethod
    def validate_file(file: UploadFile):
        allowed_types = [
            "image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp",
            "image/x-icon", "image/avif", "image/tiff", "image/heif", "image/heic",
            "video/mp4", "video/quicktime", "video/x-msvideo", "video/x-flv",
            "video/webm", "video/avi", "video/mpeg", "video/x-matroska",
            "application/pdf",
            "application/zip", "application/x-zip-compressed",
            "application/octet-stream"
        ]
        
        # Validación especial para archivos ZIP
        file_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
        if file_ext == ".zip":
            zip_types = ["application/zip", "application/x-zip-compressed", "application/octet-stream"]
            if file.content_type not in zip_types:
                pass  # Permitir por la extensión
        elif file.content_type not in allowed_types:
            # También verificar por extensión para tipos MIME no estándar
            if file_ext in ['.avif', '.heif', '.heic']:
                pass  # Permitir formatos AVIF/HEIF por extensión
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tipo de archivo no permitido: {file.content_type}. "
                           f"Archivo: {file.filename}"
                )
    
    @staticmethod
    async def save_file(
        file: UploadFile, 
        client_name: str, 
        optimize: bool = True,
    ) -> str:
        """
        Guarda archivo con opción de optimización
        
        Args:
            file: Archivo a guardar
            client_name: Nombre del cliente
            optimize: Si True, optimiza imágenes/videos
        
        Returns:
            str con:
            - filename: Nombre COMPLETO del archivo guardado (para BD y frontend)
        """
        FileService.validate_file(file)
        
        logger.info(f"Guardando archivo: {file.filename} para cliente: {client_name}, optimizar: {optimize}")
        
        # Optimizar si está habilitado
        if optimize and FileOptimizer.should_optimize(file.content_type, file.filename):
            logger.info(f"Optimizando archivo: {file.filename}")
            
            optimized_content, optimized_filename, optimized_content_type = (
                await FileOptimizer.optimize_file(file, optimize=True)
            )
            
            # Generar nombre único manteniendo la extensión
            file_ext = Path(optimized_filename).suffix.lower()
            optimized_uuid_name = f"{uuid.uuid4()}{file_ext}"
            
            # Guardar versión optimizada
            saved_filename = await FileService._save_local_bytes(
                optimized_content,
                optimized_uuid_name,
                client_name,
                optimized_content_type
            )
            
            return saved_filename
        else:
            # Guardar sin optimizar
            logger.info(f"Guardando sin optimizar: {file.filename}")
            
            content = await file.read()
            original_file_ext = Path(file.filename).suffix.lower()
            uuid_name = f"{uuid.uuid4()}{original_file_ext}"
            
            saved_filename = await FileService._save_local_bytes(
                content,
                uuid_name,
                client_name,
                file.content_type
            )
            
            return saved_filename
    
    @staticmethod
    async def _save_local_bytes(
        content: bytes,
        filename: str,
        client_name: str,
        content_type: str
    ) -> str:
        """Guarda bytes en sistema local y devuelve el nombre del archivo"""
        try:
            uploads_path = Path(settings.UPLOADS)
            client_path = uploads_path / client_name
            client_path.mkdir(parents=True, exist_ok=True)
            
            file_path = client_path / filename
            
            with open(file_path, "wb") as f:
                f.write(content)
            
            file_size_mb = len(content) / (1024 * 1024)
            logger.info(
                f"[LOCAL] Archivo guardado: {filename} "
                f"({file_size_mb:.2f} MB, {content_type}) "
                f"en: {file_path}"
            )
            
            return filename  # Devuelve solo el nombre del archivo
            
        except Exception as e:
            logger.error(f"Error guardando archivo {filename}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al guardar archivo: {str(e)}"
            )
    
    @staticmethod
    async def _save_local(file: UploadFile, filename: str, client_name: str) -> str:
        """Método original compatible - devuelve solo el nombre del archivo"""
        content = await file.read()
        return await FileService._save_local_bytes(
            content, filename, client_name, file.content_type
        )
    
    @staticmethod
    def delete_file(filename: str, client_name: str):
        """Elimina archivo del almacenamiento local"""
        FileService._delete_local(filename, client_name)

    @staticmethod
    def _delete_local(filename: str, client_name: str):
        try:
            uploads_path = Path(settings.UPLOADS)
            file_path = uploads_path / client_name / filename
            if file_path.exists():
                file_path.unlink()
                logger.info(f"[LOCAL] Archivo eliminado: {filename}")
        except Exception as e:
            logger.error(f"[LOCAL] Error al eliminar archivo {filename}: {e}")

    @staticmethod
    def get_file_url(filename: str, client_name: str) -> str:
        """Obtiene ruta local del archivo"""
        return FileService._get_local_url(filename, client_name)

    @staticmethod
    def _get_local_url(filename: str, client_name: str) -> str:
        uploads_path = Path(settings.UPLOADS)
        file_path = uploads_path / client_name / filename
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Archivo no encontrado: {filename}"
            )
        return str(file_path.absolute())
    
    @staticmethod
    async def get_media(filename: str, client_name: str):
        """
        Devuelve el archivo desde almacenamiento local
        """
        try:
            uploads_path = Path(settings.UPLOADS)
            file_path = uploads_path / client_name / filename
            
            if not file_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Archivo no encontrado: {filename}"
                )
            
            # Determinar content-type por extensión del archivo
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = "application/octet-stream"
            
            # Configurar Content-Disposition según el tipo de archivo
            if content_type.startswith("image/"):
                content_disposition = "inline"
            elif content_type.startswith("video/"):
                content_disposition = "inline"
            else:
                content_disposition = f'attachment; filename="{filename}"'
            
            logger.info(f"[LOCAL] Sirviendo: {filename} | Type: {content_type}")
            
            return FileResponse(
                file_path,
                media_type=content_type,
                headers={
                    "Content-Disposition": content_disposition,
                    "Cache-Control": "public, max-age=3600",
                    "Access-Control-Allow-Origin": "*"
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error sirviendo archivo {filename}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al obtener archivo: {str(e)}"
            )

    @staticmethod
    def list_client_files(client_name: str, prefix: str = ""):
        """Lista archivos de un cliente en almacenamiento local"""
        try:
            uploads_path = Path(settings.UPLOADS)
            client_path = uploads_path / client_name
            
            if not client_path.exists():
                return []
            
            files = []
            for item in client_path.iterdir():
                if item.is_file() and item.name.startswith(prefix):
                    stats = item.stat()
                    files.append({
                        "filename": item.name,  # Nombre completo
                        "name": item.stem,  # Sin extensión
                        "extension": item.suffix.lower().replace('.', ''),
                        "size": stats.st_size,
                        "last_modified": stats.st_mtime,
                        "path": str(item.relative_to(uploads_path))
                    })
            
            return files
            
        except Exception as e:
            logger.error(f"[LOCAL] Error al listar archivos: {e}")
            return []
    
    @staticmethod
    def get_file_info(filename: str, client_name: str) -> Dict:
        """Obtiene información detallada de un archivo"""
        try:
            uploads_path = Path(settings.UPLOADS)
            file_path = uploads_path / client_name / filename
            
            if not file_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Archivo no encontrado: {filename}"
                )
            
            stats = file_path.stat()
            content_type, encoding = mimetypes.guess_type(filename)
            
            return {
                "filename": filename,
                "name": file_path.stem,
                "extension": file_path.suffix.lower().replace('.', ''),
                "content_type": content_type or "application/octet-stream",
                "encoding": encoding,
                "size": stats.st_size,
                "size_mb": stats.st_size / (1024 * 1024),
                "created": stats.st_ctime,
                "modified": stats.st_mtime,
                "path": str(file_path.absolute())
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error obteniendo info de archivo {filename}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al obtener información del archivo: {str(e)}"
            )