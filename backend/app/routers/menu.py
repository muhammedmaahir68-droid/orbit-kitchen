from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..database import SessionLocal
from ..models import MenuCategory, MenuItem, KitchenStation, Branch, uid
from .. import events

router = APIRouter(prefix="/api/v1/menu", tags=["menu"])


# ── GET MENU (customer-facing, shows all items with is_available flag) ─────────

@router.get("")
async def get_menu(branch_id: str):
    """Return all menu items for a branch (available + unavailable, so customers see SOLD OUT)."""
    async with SessionLocal() as db:
        cat_result = await db.execute(select(MenuCategory).where(MenuCategory.branch_id == branch_id))
        categories = cat_result.scalars().all()
        item_result = await db.execute(select(MenuItem).where(MenuItem.branch_id == branch_id))
        items = item_result.scalars().all()

    items_by_cat: dict[str, list] = {}
    for i in items:
        items_by_cat.setdefault(i.category_id, []).append({
            "id": i.id, "name": i.name, "price": i.price,
            "avg_prep_seconds": i.avg_prep_seconds, "is_available": i.is_available,
        })

    return [
        {"id": c.id, "name": c.name, "items": items_by_cat.get(c.id, [])}
        for c in categories
    ]


# ── CATEGORIES ─────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    branch_id: str
    name: str


@router.post("/categories")
async def create_category(body: CategoryCreate):
    async with SessionLocal() as db:
        cat = MenuCategory(id=uid(), branch_id=body.branch_id, name=body.name.strip())
        db.add(cat)
        await db.commit()
        return {"id": cat.id, "name": cat.name, "branch_id": cat.branch_id}


@router.delete("/categories/{cat_id}")
async def delete_category(cat_id: str):
    async with SessionLocal() as db:
        cat = await db.get(MenuCategory, cat_id)
        if not cat:
            raise HTTPException(404, "Category not found")
        # delete all items in this category first
        items = await db.execute(select(MenuItem).where(MenuItem.category_id == cat_id))
        for item in items.scalars().all():
            await db.delete(item)
        await db.delete(cat)
        await db.commit()
        return {"deleted": cat_id}


@router.delete("/reset")
async def reset_menu(branch_id: str):
    """Wipe ALL categories and items for a branch so the cashier can start fresh."""
    async with SessionLocal() as db:
        items = await db.execute(select(MenuItem).where(MenuItem.branch_id == branch_id))
        for item in items.scalars().all():
            await db.delete(item)
        cats = await db.execute(select(MenuCategory).where(MenuCategory.branch_id == branch_id))
        for cat in cats.scalars().all():
            await db.delete(cat)
        await db.commit()
        return {"reset": True, "branch_id": branch_id}


# ── MENU ITEMS ─────────────────────────────────────────────────────────────────

class ItemCreate(BaseModel):
    branch_id: str
    category_id: str
    name: str
    price: float
    avg_prep_seconds: int = 600
    station_name: str = "Main Kitchen"   # cashier picks station by name


@router.post("/items")
async def create_item(body: ItemCreate):
    async with SessionLocal() as db:
        # Resolve station by name (or pick the first one)
        st_result = await db.execute(
            select(KitchenStation).where(
                KitchenStation.branch_id == body.branch_id,
                KitchenStation.name == body.station_name,
            )
        )
        station = st_result.scalars().first()
        if not station:
            # fall back to any station
            any_st = await db.execute(select(KitchenStation).where(KitchenStation.branch_id == body.branch_id))
            station = any_st.scalars().first()
        if not station:
            raise HTTPException(400, "No kitchen stations found. Run initial setup.")

        item = MenuItem(
            id=uid(), branch_id=body.branch_id, category_id=body.category_id,
            station_id=station.id, name=body.name.strip(),
            price=body.price, avg_prep_seconds=body.avg_prep_seconds, is_available=True,
        )
        db.add(item)
        await db.commit()
        await events.publish(
            "MenuItemAdded", "menu_item", item.id,
            {"name": item.name, "price": item.price, "is_available": True},
            branch_id=body.branch_id,
        )
        return {"id": item.id, "name": item.name, "price": item.price, "is_available": True}


class ItemUpdate(BaseModel):
    name: str | None = None
    price: float | None = None
    avg_prep_seconds: int | None = None


@router.patch("/items/{item_id}")
async def update_item(item_id: str, body: ItemUpdate):
    async with SessionLocal() as db:
        item = await db.get(MenuItem, item_id)
        if not item:
            raise HTTPException(404, "Item not found")
        if body.name is not None:
            item.name = body.name.strip()
        if body.price is not None:
            item.price = body.price
        if body.avg_prep_seconds is not None:
            item.avg_prep_seconds = body.avg_prep_seconds
        await db.commit()
        return {"id": item.id, "name": item.name, "price": item.price}


@router.delete("/items/{item_id}")
async def delete_item(item_id: str):
    async with SessionLocal() as db:
        item = await db.get(MenuItem, item_id)
        if not item:
            raise HTTPException(404, "Item not found")
        branch_id = item.branch_id
        name = item.name
        await db.delete(item)
        await db.commit()
        await events.publish(
            "MenuItemRemoved", "menu_item", item_id,
            {"name": name, "is_available": False},
            branch_id=branch_id,
        )
        return {"deleted": item_id}


# ── AVAILABILITY TOGGLE ────────────────────────────────────────────────────────

class AvailabilityUpdate(BaseModel):
    is_available: bool


@router.patch("/items/{item_id}/availability")
async def set_item_availability(item_id: str, body: AvailabilityUpdate):
    """Kitchen / Cashier marks item sold-out or available. Broadcasts live update."""
    async with SessionLocal() as db:
        item = await db.get(MenuItem, item_id)
        if not item:
            raise HTTPException(404, "Item not found")
        item.is_available = body.is_available
        await db.commit()
        await events.publish(
            "MenuItemAvailabilityChanged", "menu_item", item_id,
            {"name": item.name, "is_available": body.is_available},
            branch_id=item.branch_id,
        )
        return {"id": item_id, "is_available": item.is_available}


# ── STATIONS (for cashier dropdown) ───────────────────────────────────────────

@router.get("/stations")
async def get_stations(branch_id: str):
    async with SessionLocal() as db:
        result = await db.execute(select(KitchenStation).where(KitchenStation.branch_id == branch_id))
        stations = result.scalars().all()
        return [{"id": s.id, "name": s.name} for s in stations]


# ── UPI SETTINGS ───────────────────────────────────────────────────────────────

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
