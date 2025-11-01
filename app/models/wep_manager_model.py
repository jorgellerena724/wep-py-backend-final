from typing import TYPE_CHECKING, Optional
from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy import Text

if TYPE_CHECKING:
    from app.models.wep_manager_category_model import WepManagerCategoryModel


class WepManagerModel(SQLModel, table=True):
    __tablename__ = "manager"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str        = Field(max_length=100, nullable=False)
    description : str = Field(sa_type=Text(), nullable=False)
    charge : str      = Field(max_length=100, nullable=False)
    photo: str        = Field(max_length=80, nullable=True)
    manager_category_id: Optional[int] = Field(foreign_key="manager_category.id", nullable=True)
    
    manager_category: Optional["WepManagerCategoryModel"] = Relationship(
        back_populates="managers",
        sa_relationship_kwargs={"lazy": "joined"}  # Carga automática
    )
      
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepManagerModel(nombre={self.title})>"
    