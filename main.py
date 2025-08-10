from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from app.api.router import api_router
from app.config.config import settings
from app.config.database import init_database, migrate_all_tenant_schemas
from fastapi.staticfiles import StaticFiles
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Configuración de middleware y rutas
app.mount("/uploads", StaticFiles(directory=settings.UPLOADS), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

app.include_router(api_router, prefix="/api", tags=["API Router"])

if __name__ == "__main__":
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=settings.SERVER_PORT,
            workers=4,
            reload=True,
            log_level="info"
        )