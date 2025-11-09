import json
from fastapi import APIRouter, File, UploadFile, Form, Depends, HTTPException, status
from typing import Dict, Optional, List
from sqlmodel import SQLModel, select, Session
from app.api.endpoints.token import verify_token, get_tenant_session
from app.models.wep_user_model import WepUserModel
from app.models.wep_product_model import WepProductModel
from app.services.file_service import FileService
from sqlalchemy.orm import selectinload

class CategoryRead(SQLModel):
    id: int
    title: str

class ProductRead(SQLModel):
    id: int
    title: str
    description: str
    category: CategoryRead
    cal_url: Optional[str]
    variants: List[Dict]
    files: List[Dict]

router = APIRouter()

@router.post("/", response_model=WepProductModel)
async def create_product(
    title: str = Form(..., max_length=100),
    description: str = Form(...),
    category_id: int = Form(...),
    cal_url: str = Form(""),  # Cambiar a string vacío por defecto
    files: List[UploadFile] = File(...),  # Múltiples archivos
    file_titles: str = Form(...),  # JSON con títulos para cada archivo
    variants: str = Form(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Procesar variantes
        variants_list = []
        if variants:
            try:
                variants_data = json.loads(variants)
                if not isinstance(variants_data, list):
                    raise ValueError("Las variantes deben ser una lista")
                    
                for item in variants_data:
                    if 'description' not in item or 'price' not in item:
                        raise ValueError("Cada variante debe tener 'description' y 'price'")
                    variants_list.append(item)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="JSON inválido en variantes")
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        # Procesar títulos de archivos
        try:
            titles_data = json.loads(file_titles)
            if not isinstance(titles_data, list):
                raise ValueError("file_titles debe ser una lista")
            if len(titles_data) != len(files):
                raise ValueError("La cantidad de títulos debe coincidir con la cantidad de archivos")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="JSON inválido en file_titles")
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Validar y guardar archivos
        saved_files = []
        for i, file in enumerate(files):
            FileService.validate_file(file)
            filename = await FileService.save_file(file, current_user.client)
            
            # Crear objeto ProductImage
            saved_files.append({
                "title": titles_data[i],
                "media": filename
            })

        # Crear producto
        product = WepProductModel(
            title=title,
            cal_url=cal_url,
            description=description,
            category_id=category_id,
            variants=variants_list,
            files=saved_files
        )
        
        db.add(product)
        db.commit()
        db.merge(product)
        
        return product
        
    except Exception as e:
        db.rollback()
        # Limpiar archivos guardados en caso de error
        for saved_file in saved_files:
            try:
                FileService.delete_file(saved_file["media"], current_user.client)
            except:
                pass
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
    cal_url: str = Form(""),  # Cambiar a string vacío por defecto
    files: Optional[List[UploadFile]] = File(None),
    file_titles: Optional[str] = Form(None),
    existing_files: Optional[str] = Form(None),  # Archivos existentes que se mantienen
    variants: Optional[str] = Form(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        product = db.get(WepProductModel, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        # Actualizar campos básicos
        if title is not None:
            product.title = title
        if description is not None:
            product.description = description
        if category_id is not None:
            product.category_id = category_id
        # Siempre actualizar cal_url, incluso si es string vacío
        product.cal_url = cal_url
        if variants is not None:
            variants_list = json.loads(variants)
            if not isinstance(variants_list, list):
                raise HTTPException(400, "Las variantes deben ser una lista")
            product.variants = variants_list

        # Actualizar archivos - NUEVA LÓGICA MEJORADA
        if existing_files is not None or files is not None:
            try:
                new_files_list = []
                
                # 1. Procesar archivos existentes que se mantienen
                if existing_files:
                    existing_files_data = json.loads(existing_files)
                    if not isinstance(existing_files_data, list):
                        raise ValueError("existing_files debe ser una lista")
                    
                    for existing_file in existing_files_data:
                        new_files_list.append({
                            "title": existing_file.get("title", ""),
                            "media": existing_file["path"]
                        })
                
                # 2. Procesar archivos nuevos
                if files:
                    if not file_titles:
                        raise ValueError("file_titles es requerido cuando se envían archivos nuevos")
                    
                    titles_data = json.loads(file_titles)
                    if not isinstance(titles_data, list):
                        raise ValueError("file_titles debe ser una lista")
                    if len(titles_data) != len(files):
                        raise ValueError(f"La cantidad de títulos ({len(titles_data)}) debe coincidir con la cantidad de archivos nuevos ({len(files)})")
                    
                    for i, file in enumerate(files):
                        FileService.validate_file(file)
                        filename = await FileService.save_file(file, current_user.client)
                        new_files_list.append({
                            "title": titles_data[i],
                            "media": filename
                        })
                
                # 3. Eliminar archivos que ya no están en la nueva lista
                current_media_files = [f["media"] for f in new_files_list]
                for old_file in product.files:
                    if old_file["media"] not in current_media_files:
                        try:
                            FileService.delete_file(old_file["media"], current_user.client)
                        except:
                            pass
                
                # 4. Actualizar la lista de archivos del producto
                product.files = new_files_list
                
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"JSON inválido: {str(e)}")
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        db.commit()
        db.merge(product)
        return product

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
    product = db.exec(
         select(WepProductModel)
         .options(selectinload(WepProductModel.category))
         .where(WepProductModel.id == product_id)
     ).first()
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
        # Eliminar todos los archivos asociados
        for file_data in product.files:
            try:
                FileService.delete_file(file_data["media"], current_user.client)
            except:
                pass  # Continuar aunque falle la eliminación de algún archivo
        
        # Eliminar registro
        db.delete(product)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando producto: {str(e)}"
        )