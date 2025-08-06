from typing import TYPE_CHECKING, Optional
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .wep_product_model import WepProductModel

class WepCategoryModel(SQLModel, table=True):
    __tablename__ = "category"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(max_length=100, nullable=False)
    
    products: list["WepProductModel"] = Relationship(back_populates="category")
   
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepCategoryModel(nombre={self.title})>"