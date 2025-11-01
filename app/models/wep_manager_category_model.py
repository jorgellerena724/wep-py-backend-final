from typing import TYPE_CHECKING, Optional
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .wep_manager_model import WepManagerModel

class WepManagerCategoryModel(SQLModel, table=True):
    __tablename__ = "manager_category"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(max_length=100, nullable=False)
    
    managers: list["WepManagerModel"] = Relationship(back_populates="manager_category")
   
    class Config:
        from_attributes = True

    def __repr__(self):
        return f"<WepManagerCategoryModel(nombre={self.title})>"