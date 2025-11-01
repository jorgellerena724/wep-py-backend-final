from fastapi import APIRouter

from .endpoints import header
from .endpoints import token
from .endpoints import user
from .endpoints import images
from .endpoints import carrousel
from .endpoints import category
from .endpoints import company
from .endpoints import contact
from .endpoints import manager
from .endpoints import reviews
from .endpoints import news
from .endpoints import products
from .endpoints import emails
from .endpoints import publications
from .endpoints import publication_category
from .endpoints import manager_category

# Crear el router principal para la API v1
api_router = APIRouter()

# Registrar subrouters (endpoints específicos)
api_router.include_router(header.router, prefix="/header", tags=["Header"])
api_router.include_router(token.router, prefix="/auth", tags=["Login"])
api_router.include_router(user.router, prefix="/users", tags=["User"])
api_router.include_router(images.router, prefix="/images", tags=["Images"])
api_router.include_router(carrousel.router, prefix="/carrousel", tags=["Carrousel"])
api_router.include_router(category.router, prefix="/category", tags=["Category"])
api_router.include_router(company.router, prefix="/company", tags=["Company"])
api_router.include_router(contact.router, prefix="/contact", tags=["Contact"])
api_router.include_router(manager.router, prefix="/manager", tags=["Manager"])
api_router.include_router(manager_category.router, prefix="/manager-category", tags=["Categoria manager"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])
api_router.include_router(news.router, prefix="/news", tags=["News"])
api_router.include_router(products.router, prefix="/product", tags=["Products"])
api_router.include_router(publication_category.router, prefix="/publication-category", tags=["Categoria publicaciones"])
api_router.include_router(publications.router, prefix="/publications", tags=["Publicaciones"])
api_router.include_router(emails.router, prefix="/emails", tags=["emails"])