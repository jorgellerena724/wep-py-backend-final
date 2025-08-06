from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, status
from typing import Optional, List
from sqlmodel import SQLModel, select
from app.api.endpoints.token import verify_token, get_tenant_session
from app.models.wep_user_model import WepUserModel
from app.models.wep_product_model import WepProductModel
from app.services.file_service import FileService
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

class CategoryRead(SQLModel):
    id: int
    title: str

class ProductRead(SQLModel):
    id: int
    title: str
    description: str
    photo: str
    category: CategoryRead
    price: float

router = APIRouter()

@router.post("/", response_model=WepProductModel)
async def create_product(
    title: str = Form(..., max_length=100),
    description: str = Form(...),
    category_id: int = Form(...),
    photo: UploadFile = Form(...),
    price: Optional[float] = Form(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    # Validar imagen
    FileService.validate_file(photo)
    
    try:
        # Guardar imagen (solo nombre)
        photo_filename = await FileService.save_file(photo)
        
        # Crear registro
        product = WepProductModel(
            title=title,
            description=description,
            photo=photo_filename,
            category_id=category_id,
            price=price
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creando producto: {str(e)}"
        )

@router.patch("/{product_id}", response_model=WepProductModel)
async def update_product(
    product_id: int,
    title: Optional[str] = Form(None, max_length=100),
    description: Optional[str] = Form(None),
    category_id: Optional[int] = Form(None),
    photo: Optional[UploadFile] = Form(None),
    price: Optional[float] = Form(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Obtener el producto existente
        product = db.get(WepProductModel, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        # Actualizar campos si se proporcionan
        if title is not None:
            product.title = title
        if description is not None:
            product.description = description
        if price is not None:
            product.price = price
        if category_id is not None:
            product.category_id = category_id

        # Procesar imagen si se proporciona
        if photo is not None:
            # Validar tipo de imagen
            FileService.validate_file(photo)
            
            # Eliminar imagen anterior si existe
            if product.photo:
                FileService.delete_file(product.photo, current_user.client)
            
            # Guardar nueva imagen
            new_filename = await FileService.save_file(photo)
            product.photo = new_filename

        # Confirmar cambios en la base de datos
        db.commit()
        db.refresh(product)
        
        return product

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el producto: {str(e)}"
        )

@router.get("/", response_model=List[ProductRead])
def get_products(
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    # Consulta con carga de relación category y ordenamiento por id
    query = (
        select(WepProductModel)
        .options(selectinload(WepProductModel.category))
        .order_by(WepProductModel.id)
    )
    
    products = db.exec(query).all()
    return [ProductRead.model_validate(p) for p in products]

@router.get("/{product_id}", response_model=WepProductModel)
def get_product(
    product_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    product = db.get(WepProductModel, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product

@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    product = db.get(WepProductModel, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    try:
        # Eliminar imagen asociada
        FileService.delete_file(product.photo, current_user.client)
        
        # Eliminar registro
        db.delete(product)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando producto: {str(e)}"
        )