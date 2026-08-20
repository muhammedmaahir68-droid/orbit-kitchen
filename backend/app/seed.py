"""
DEVELOPMENT-ONLY seed data. This creates one restaurant/branch/tables/stations/menu
so the vertical slice is runnable immediately. This is NOT synthetic analytics data —
it is just the static catalog (tables, stations, menu) a real restaurant would enter
once through an onboarding flow. No order/forecast data is faked here.
"""
from sqlalchemy import select
from .database import SessionLocal
from .models import Restaurant, Branch, RestaurantTable, KitchenStation, MenuCategory, MenuItem, StaffUser, uid
from .security import hash_password


async def seed():
    async with SessionLocal() as db:
        existing = await db.execute(select(Restaurant))
        if existing.scalars().first():
            return  # already seeded

        restaurant = Restaurant(id=uid(), name="Orbit Demo Kitchen")
        branch = Branch(id=uid(), restaurant_id=restaurant.id, name="Main Branch")
        db.add_all([restaurant, branch])
        await db.flush()

        tables = [RestaurantTable(id=uid(), branch_id=branch.id, number=n, capacity=4) for n in range(1, 6)]
        db.add_all(tables)

        stations = {
            name: KitchenStation(id=uid(), branch_id=branch.id, name=name)
            for name in ["Main Kitchen", "Fry Station", "Beverage Station", "Dessert Station"]
        }
        db.add_all(stations.values())
        await db.flush()

        category = MenuCategory(id=uid(), branch_id=branch.id, name="Mains")
        db.add(category)
        await db.flush()

        menu_items = [
            MenuItem(id=uid(), branch_id=branch.id, category_id=category.id, station_id=stations["Main Kitchen"].id,
                     name="Chicken Biryani", price=8.5, avg_prep_seconds=720),
            MenuItem(id=uid(), branch_id=branch.id, category_id=category.id, station_id=stations["Fry Station"].id,
                     name="French Fries", price=3.0, avg_prep_seconds=300),
            MenuItem(id=uid(), branch_id=branch.id, category_id=category.id, station_id=stations["Beverage Station"].id,
                     name="Lime Juice", price=2.0, avg_prep_seconds=120),
            MenuItem(id=uid(), branch_id=branch.id, category_id=category.id, station_id=stations["Dessert Station"].id,
                     name="Ice Cream", price=2.5, avg_prep_seconds=90),
        ]
        db.add_all(menu_items)
        await db.commit()

        # Demo staff logins — CHANGE THESE before any real deployment.
        staff = [
            StaffUser(id=uid(), branch_id=branch.id, username="kitchen", name="Kitchen Staff",
                      role="KITCHEN", password_hash=hash_password("kitchen123")),
            StaffUser(id=uid(), branch_id=branch.id, username="cashier", name="Cashier",
                      role="CASHIER", password_hash=hash_password("cashier123")),
        ]
        db.add_all(staff)
        await db.commit()

        print(f"Seeded restaurant={restaurant.id} branch={branch.id}")
        print(f"Table IDs: {[t.id for t in tables]}")
        print(f"Menu item IDs: {[(m.name, m.id) for m in menu_items]}")
        print("Demo logins: kitchen/kitchen123, cashier/cashier123")
        return restaurant, branch, tables, menu_items
