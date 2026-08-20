from fastapi import APIRouter
from sqlalchemy import select

from ..database import SessionLocal
from ..models import MenuCategory, MenuItem

router = APIRouter(prefix="/api/v1/menu", tags=["menu"])


@router.get("")
async def get_menu(branch_id: str):
    async with SessionLocal() as db:
        cat_result = await db.execute(select(MenuCategory).where(MenuCategory.branch_id == branch_id))
        categories = cat_result.scalars().all()
        item_result = await db.execute(
            select(MenuItem).where(MenuItem.branch_id == branch_id, MenuItem.is_available == True)  # noqa: E712
        )
        items = item_result.scalars().all()

    items_by_category: dict[str, list] = {}
    for i in items:
        items_by_category.setdefault(i.category_id, []).append({
            "id": i.id, "name": i.name, "price": i.price, "avg_prep_seconds": i.avg_prep_seconds,
        })

    return [
        {"id": c.id, "name": c.name, "items": items_by_category.get(c.id, [])}
        for c in categories
    ]
