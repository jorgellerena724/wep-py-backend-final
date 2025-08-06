from typing import Generic, TypeVar, List, Optional
from pydantic import BaseModel
from urllib.parse import urlencode

T = TypeVar('T')

class PaginationParams(BaseModel):
    page: int = 1
    size: int = 3000
    search: Optional[str] = None
    sort: Optional[str] = None
    order: Optional[str] = "asc"

class PaginationLinks(BaseModel):
    first: Optional[str] = None
    prev: Optional[str] = None
    next: Optional[str] = None
    last: Optional[str] = None

class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    total_pages: int
    current_page: int
    page_size: int
    has_next: bool
    has_prev: bool
    links: PaginationLinks
    results: List[T]

    @classmethod
    def create(cls, items: List[T], total: int, params: PaginationParams, base_url: str):
        total_pages = (total + params.size - 1) // params.size
        
        # Crear links de paginación
        links = PaginationLinks(
            first=f"{base_url}?{urlencode({'page': 1, 'size': params.size})}",
            last=f"{base_url}?{urlencode({'page': total_pages, 'size': params.size})}",
        )
        
        if params.page > 1:
            links.prev = f"{base_url}?{urlencode({'page': params.page - 1, 'size': params.size})}"
        
        if params.page < total_pages:
            links.next = f"{base_url}?{urlencode({'page': params.page + 1, 'size': params.size})}"

        return cls(
            total=total,
            total_pages=total_pages,
            current_page=params.page,
            page_size=params.size,
            has_next=params.page < total_pages,
            has_prev=params.page > 1,
            links=links,
            results=items,
        )