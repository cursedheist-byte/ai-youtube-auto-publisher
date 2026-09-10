import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models import Category, DriveSource, User
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate
router = APIRouter(prefix="/api/categories", tags=["categories"])
admin_router = APIRouter(prefix="/api/admin/categories", tags=["categories"], dependencies=[Depends(require_admin)])

def normalized(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).casefold()

def _save(db, category):
    try:
        db.add(category); db.commit(); db.refresh(category); return category
    except Exception:
        db.rollback(); raise HTTPException(status_code=409, detail="A category with that name already exists.")

@router.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Category).order_by(Category.name).all()

@admin_router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    return _save(db, Category(name=payload.name.strip(), normalized_name=normalized(payload.name)))

@admin_router.patch("/{category_id}", response_model=CategoryOut)
def update_category(category_id: uuid.UUID, payload: CategoryUpdate, db: Session = Depends(get_db)):
    category = db.get(Category, category_id)
    if category is None: raise HTTPException(404, "Category not found")
    category.name = payload.name.strip(); category.normalized_name = normalized(payload.name)
    return _save(db, category)

@admin_router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: uuid.UUID, db: Session = Depends(get_db)):
    category = db.get(Category, category_id)
    if category is None: raise HTTPException(404, "Category not found")
    if db.query(DriveSource.id).filter(DriveSource.category_id == category_id).first():
        raise HTTPException(409, "This category is assigned to a Drive source. Reassign the source before deleting it.")
    db.delete(category); db.commit()
