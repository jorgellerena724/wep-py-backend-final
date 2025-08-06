from typing import TYPE_CHECKING, Optional
from sqlmodel import Field, Relationship, SQLModel
from datetime import date
from sqlalchemy import Text

if TYPE_CHECKING:
    from .wep_category_model import WepCategoryModel

class WepProductModel(SQLModel, table=True):
    __tablename__ = "product"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str        = Field(max_length=100, nullable=False)
    description : str = Field(sa_type=Text(), nullable=False)
    photo: str        = Field(max_length=80, nullable=False)
    category_id: int = Field(foreign_key="category.id", nullable=False)
    price: Optional[float] = Field(default=None)
    
    category: Optional["WepCategoryModel"] = Relationship(
        back_populates="products",
        sa_relationship_kwargs={"lazy": "joined"}  # Carga automática
    )
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepProductModel(nombre={self.title})>"