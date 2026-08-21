from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..database import SessionLocal
from ..models import MenuCategory, MenuItem, Branch
from .. import events

router = APIRouter(prefix="/api/v1/menu", tags=["menu"])


@router.get("")
async def get_menu(branch_id: str):
    """Customer-facing menu – only available items returned."""
    async with SessionLocal() as db:
        cat_result = await db.execute(select(MenuCategory).where(MenuCategory.branch_id == branch_id))
        categories = cat_result.scalars().all()
        item_result = await db.execute(
            select(MenuItem).where(MenuItem.branch_id == branch_id)
        )
        items = item_result.scalars().all()

    items_by_category: dict[str, list] = {}
    for i in items:
        items_by_category.setdefault(i.category_id, []).append({
            "id": i.id, "name": i.name, "price": i.price,
            "avg_prep_seconds": i.avg_prep_seconds, "is_available": i.is_available,
        })

    return [
        {"id": c.id, "name": c.name, "items": items_by_category.get(c.id, [])}
        for c in categories
    ]


class AvailabilityUpdate(BaseModel):
    is_available: bool


@router.patch("/{item_id}/availability")
async def set_item_availability(item_id: str, body: AvailabilityUpdate):
    """Cashier / Kitchen can mark an item sold-out or back in stock."""
    async with SessionLocal() as db:
        item = await db.get(MenuItem, item_id)
        if not item:
            raise HTTPException(404, "Item not found")
        item.is_available = body.is_available
        await db.commit()
        # Broadcast so kitchen and customer screens refresh live
        await events.publish(
            "MenuItemAvailabilityChanged", "menu_item", item_id,
            {"name": item.name, "is_available": body.is_available},
            branch_id=item.branch_id,
        )
        return {"id": item_id, "is_available": item.is_available}


# ── UPI Settings ──────────────────────────────────────────────────────────────

@router.get("/settings/upi")
async def get_upi(branch_id: str):
    async with SessionLocal() as db:
        branch = await db.get(Branch, branch_id)
        if not branch:
            raise HTTPException(404, "Branch not found")
        return {"upi_id": branch.upi_id or ""}


class UpiUpdate(BaseModel):
    upi_id: str


@router.patch("/settings/upi")
async def set_upi(branch_id: str, body: UpiUpdate):
    async with SessionLocal() as db:
        branch = await db.get(Branch, branch_id)
        if not branch:
            raise HTTPException(404, "Branch not found")
        branch.upi_id = body.upi_id.strip()
        await db.commit()
        return {"upi_id": branch.upi_id}
