from datetime import date
from fastapi import APIRouter, File, UploadFile, Form, Depends, HTTPException
from typing import Optional
from sqlmodel import select, Session
from app.api.endpoints.token import verify_token, get_tenant_session
from app.models.wep_user_model import WepUserModel
from app.models.wep_news_model import WepNewsModel
from app.services.file_service import FileService
from sqlalchemy.orm import Session
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

router = APIRouter()

@router.post("/", response_model=WepNewsModel)
async def create_news(
    title: str = Form(..., max_length=100),
    description: str = Form(...),
    fecha: date = Form(...),
    photo: UploadFile = Form(...),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    # Validar imagen
    FileService.validate_file(photo)
    
    try:
        # Guardar imagen (solo nombre)
        photo_filename = await FileService.save_file(photo, current_user.client)
        
        # Crear registro
        news = WepNewsModel(title=title, description=description,fecha=fecha, photo=photo_filename)
        db.add(news)
        db.commit()
        db.refresh(news)
        return news
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creando news: {str(e)}"
        )


@router.patch("/{news_id}", response_model=WepNewsModel)
async def update_news(
    news_id: int,
    title: Optional[str] = Form(None, max_length=100),
    description: Optional[str] = Form(None),
    fecha: Optional[date] = Form(None),
    status: Optional[bool] = Form(None),
    photo: Optional[UploadFile] = File(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Obtener la noticia existente
        news = db.get(WepNewsModel, news_id)
        if not news:
            raise HTTPException(status_code=404, detail="News no encontrado")

        # Actualizar campos proporcionados
        if title is not None:
            news.title = title
        if description is not None:
            news.description = description
        if fecha is not None:
            news.fecha = fecha
        if status is not None:
            news.status = status

        # Procesar imagen si se proporciona
        if photo is not None:
            FileService.validate_file(photo)
            if news.photo:
                FileService.delete_file(news.photo, current_user.client)
            new_filename = await FileService.save_file(photo, current_user.client)
            news.photo = new_filename

        # Confirmar cambios
        db.commit()
        db.refresh(news)
        
        return news

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    except HTTPException:
        # Re-lanzar excepciones HTTP que ya estamos manejando
        db.rollback()
        raise

    except Exception as e:
        # Revertir cambios en caso de cualquier otro error
        db.rollback()
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el news: {str(e)}"
        )

@router.get("/", response_model=list[WepNewsModel])
def get_news( current_user: WepUserModel = Depends(verify_token),db: Session = Depends(get_tenant_session)):

    source = getattr(current_user, 'source', 'unknown')
    
    if source == "website":
        query = select(WepNewsModel).where(WepNewsModel.status == True).order_by(WepNewsModel.id)
    else:
        # Para otros usuarios, no filtrar (devolver todo)
        query = select(WepNewsModel).order_by(WepNewsModel.id)
    
    news = db.exec(query).all()
    return news

@router.get("/{news_id}", response_model=WepNewsModel)
def get_news(news_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)):

    news = db.get(WepNewsModel, news_id)
    if not news:
        raise HTTPException(status_code=404, detail="News no encontrado")
    return news

@router.delete("/{news_id}", status_code=204)
def delete_news(news_id: int, current_user: WepUserModel = Depends(verify_token),
     db: Session = Depends(get_tenant_session)):
    
    news = db.get(WepNewsModel, news_id)
    if not news:
        raise HTTPException(status_code=404, detail="News no encontrado")
    
    try:
        # Eliminar imagen asociada
        FileService.delete_file(news.photo, current_user.client)
        
        # Eliminar registro
        db.delete(news)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando news: {str(e)}"
        )