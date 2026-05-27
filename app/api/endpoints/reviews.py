from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, status
from typing import Optional
from sqlmodel import select, Session
from app.api.endpoints.token import verify_token, get_tenant_session
from app.models.wep_user_model import WepUserModel
from app.models.wep_reviews_model import WepReviewsModel
from app.services.file_service import FileService
from sqlalchemy.orm import Session
import json
from fastapi import UploadFile, File

router = APIRouter()

GOOGLE_RATING_MAP = {
    "ONE": 1.0, "TWO": 2.0, "THREE": 3.0,
    "FOUR": 4.0, "FIVE": 5.0,
}

STAR_RATING_KEYS = ["starRating", "star_rating", "rating", "stars", "reviewRating", "score"]

def convert_rating(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        upper = stripped.upper()
        if upper in GOOGLE_RATING_MAP:
            return GOOGLE_RATING_MAP[upper]
        try:
            return float(stripped)
        except ValueError:
            return None
    return None

def _extract_rating(review: dict) -> float | None:
    for key in STAR_RATING_KEYS:
        if key in review:
            val = review[key]
            if val is not None:
                return convert_rating(val)
    return None

def parse_google_reviews(data: dict) -> list[dict]:
    reviews = data.get("reviews", [])
    result = []
    for r in reviews:
        title       = r.get("reviewer", {}).get("displayName", "").strip()
        description = r.get("comment", "").strip()
        if title and description:
            result.append({
                "title": title,
                "description": description,
                "star_rating": _extract_rating(r),
            })
    return result

PARSERS = {
    "google": parse_google_reviews,
    # "yelp": parse_yelp_reviews,  ← futuro
}

@router.post("/", response_model=WepReviewsModel)
async def create_reviews(
    title: str = Form(..., max_length=100),
    description: str = Form(...),
    photo: UploadFile = Form(...),
    star_rating: Optional[float] = Form(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    # Validar imagen
    FileService.validate_file(photo)
    
    try:
        # Guardar imagen (solo nombre)
        photo_filename = await FileService.save_file(photo, current_user.client)
        
        # Crear registro
        reviews = WepReviewsModel(title=title, description=description, photo=photo_filename, star_rating=star_rating)
        db.add(reviews)
        db.commit()
        db.merge(reviews)
        return reviews
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creando reviews: {str(e)}"
        )


@router.patch("/{reviews_id}", response_model=WepReviewsModel)
async def update_reviews(
    reviews_id: int,
    title: Optional[str] = Form(None, max_length=100),
    description: Optional[str] = Form(None),
    photo: Optional[UploadFile] = Form(None),
    star_rating: Optional[float] = Form(None),
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    try:
        # Obtener el header existente
        reviews = db.get(WepReviewsModel, reviews_id)
        if not reviews:
            raise HTTPException(status_code=404, detail="Reviews no encontrado")

        # Actualizar nombre si se proporciona
        if title is not None:
            reviews.title = title

        # Actualizar descripcion si se proporciona
        if description is not None:
            reviews.description = description

        # Actualizar star_rating si se proporciona
        if star_rating is not None:
            reviews.star_rating = star_rating

        # Procesar imagen si se proporciona
        if photo is not None:
            # Validar tipo de imagen
            FileService.validate_file(photo)
            
            # Eliminar imagen anterior si existe
            if reviews.photo:
                FileService.delete_file(reviews.photo, current_user.client)
            
            # Guardar nueva imagen
            new_filename = await FileService.save_file(photo, current_user.client)
            reviews.photo = new_filename

        # Confirmar cambios en la base de datos
        db.commit()
        db.merge(reviews)
        
        return reviews

    except HTTPException:
        # Re-lanzar excepciones HTTP que ya estamos manejando
        db.rollback()
        raise

    except Exception as e:
        # Revertir cambios en caso de cualquier otro error
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el reviews: {str(e)}"
        )

@router.get("/", response_model=list[WepReviewsModel])
def get_reviews(
    has_rating: bool = False,
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    query = select(WepReviewsModel).order_by(WepReviewsModel.id)
    if has_rating:
        query = query.where(WepReviewsModel.star_rating.isnot(None))
    return db.exec(query).all()

@router.get("/{reviews_id}", response_model=WepReviewsModel)
def get_reviews(reviews_id: int, 
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)):

    reviews = db.get(WepReviewsModel,reviews_id)
    if not reviews:
        raise HTTPException(status_code=404, detail="Reviews no encontrado")
    return reviews

@router.delete("/{reviews_id}", status_code=204)
def delete_reviews(reviews_id: int, current_user: WepUserModel = Depends(verify_token),
     db: Session = Depends(get_tenant_session)):
    
    reviews = db.get(WepReviewsModel, reviews_id)
    if not reviews:
        raise HTTPException(status_code=404, detail="Reviews no encontrado")
    
    try:
        # Eliminar imagen asociada
        FileService.delete_file(reviews.photo, current_user.client)
        
        # Eliminar registro
        db.delete(reviews)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando reviews: {str(e)}"
        )
        
@router.post("/import/")
async def import_reviews(
    file:   UploadFile = File(...),
    source: str        = Form(...),  # "google", "yelp", etc.
    current_user: WepUserModel = Depends(verify_token),
    db: Session = Depends(get_tenant_session)
):
    if source not in PARSERS:
        raise HTTPException(
            status_code=400,
            detail=f"Fuente '{source}' no soportada. Disponibles: {list(PARSERS.keys())}"
        )

    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .json")

    try:
        content = await file.read()
        data    = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON inválido")

    parsed = PARSERS[source](data)

    if not parsed:
        raise HTTPException(status_code=400, detail="No se encontraron reviews válidas en el archivo")

    created  = 0
    skipped  = 0
    existing_titles = {r.title for r in db.exec(select(WepReviewsModel)).all()}

    for item in parsed:
        if item["title"] in existing_titles:
            skipped += 1
            continue
        db.add(WepReviewsModel(
            title=item["title"],
            description=item["description"],
            photo=None,
            star_rating=item.get("star_rating"),
        ))
        existing_titles.add(item["title"])
        created += 1

    db.commit()

    return {
        "source":  source,
        "created": created,
        "skipped": skipped,
        "total":   len(parsed)
    }