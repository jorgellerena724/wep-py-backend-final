from typing import TYPE_CHECKING, Optional
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .wep_publication_model import WepPublicationModel

class WepPublicationCategoryModel(SQLModel, table=True):
    __tablename__ = "publication_category"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(max_length=100, nullable=False)
    
    publications: list["WepPublicationModel"] = Relationship(back_populates="publication_category")
   
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepPublicationCategoryModel(nombre={self.title})>"