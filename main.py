from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn
from app.api.router import api_router
from app.config.config import settings
from app.config.database import init_database
from fastapi.staticfiles import StaticFiles
import logging
import time

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log inicial del servidor
logger.info("=" * 80)
logger.info("🚀 INICIANDO SERVIDOR WEP BACKEND")
logger.info("=" * 80)

class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware para logging de todas las peticiones"""
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Log de la petición entrante
        logger.info(f"📥 {request.method} {request.url.path}")
        logger.info(f"   Host: {request.client.host if request.client else 'Unknown'}")
        logger.info(f"   Origin: {request.headers.get('origin', 'None')}")
        
        # Continuar con la petición
        response = await call_next(request)
        
        # Log de la respuesta
        process_time = time.time() - start_time
        logger.info(f"📤 {request.method} {request.url.path} - {response.status_code} ({process_time:.3f}s)")
        
        return response

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manejo del ciclo de vida de la aplicación"""
    # Inicialización al iniciar
    logger.info("Inicializando base de datos...")
    try:
        init_database()
        logger.info("✅ Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}")
        raise RuntimeError("Fallo en inicialización de BD") from e
    yield
    # Código de limpieza al apagar
    logger.info("Apagando aplicación...")

app = FastAPI(lifespan=lifespan)

# Agregar middleware de logging
app.add_middleware(LoggingMiddleware)

# Configuración de middleware y rutas
app.mount("/uploads", StaticFiles(directory=settings.UPLOADS), name="uploads")

# Log CORS origins
logger.info(f"🌐 CORS Origins configurados:")
for origin in settings.CORS_ALLOWED_ORIGINS:
    logger.info(f"   ✅ {origin}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

logger.info("✅ Middleware CORS configurado correctamente")

app.include_router(api_router, prefix="/api", tags=["API Router"])

if __name__ == "__main__":
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=settings.SERVER_PORT,
            workers=4,
            reload=settings.DEBUG,
            log_level="info"
        )