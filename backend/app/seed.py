"""
Minimal bootstrap seed. Creates one restaurant / branch / tables / kitchen-stations
and two staff accounts so the system is operational on first boot.

The MENU is intentionally left empty — the Cashier builds it from the dashboard.
"""
from sqlalchemy import select
from .database import SessionLocal
from .models import Restaurant, Branch, RestaurantTable, KitchenStation, StaffUser, uid
from .security import hash_password


async def seed():
    async with SessionLocal() as db:
        existing = await db.execute(select(Restaurant))
        if existing.scalars().first():
            return  # already bootstrapped

        restaurant = Restaurant(id=uid(), name="Orbit Kitchen")
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

        # Minimal staff — cashier should change these via the dashboard.
        staff = [
            StaffUser(id=uid(), branch_id=branch.id, username="kitchen", name="Kitchen Staff",
                      role="KITCHEN", password_hash=hash_password("kitchen123")),
            StaffUser(id=uid(), branch_id=branch.id, username="cashier", name="Cashier",
                      role="CASHIER", password_hash=hash_password("cashier123")),
        ]
        db.add_all(staff)
        await db.commit()

        print(f"Bootstrap complete: restaurant={restaurant.id} branch={branch.id}")
        print("Default logins: kitchen / kitchen123  |  cashier / cashier123")
        print("⚠️  Menu is EMPTY — log in as cashier and build the menu from the dashboard.")
