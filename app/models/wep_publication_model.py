from typing import TYPE_CHECKING, Optional
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .wep_publication_category import WepPublicationCategoryModel

class WepPublicationModel(SQLModel, table=True):
    __tablename__ = "publication"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(max_length=100, nullable=False)
    photo: Optional[str] = Field(max_length=80, nullable=True)
    file: str = Field(max_length=80, nullable=True)
    publication_category_id: int = Field(foreign_key="publication_category.id", nullable=False)
    
    publication_category: Optional["WepPublicationCategoryModel"] = Relationship(
        back_populates="publications",
        sa_relationship_kwargs={"lazy": "joined"}  # Carga automática
    )
    
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepPublicationModel(nombre={self.title})>"