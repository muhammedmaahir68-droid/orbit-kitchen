import random
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import Order, OrderItem, KitchenTask, MenuItem, RestaurantTable, OrderStatus, KitchenTaskStatus, TableStatus, uid
from .. import events

# Explicit allowed transitions. Any transition not listed here is rejected.
# This is the real backend enforcement of the lifecycle described in the spec.
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {OrderStatus.PAYMENT_PENDING, OrderStatus.PAID, OrderStatus.RESTAURANT_ACCEPTED, OrderStatus.CANCELLED, OrderStatus.COMPLETED},
    OrderStatus.PAYMENT_PENDING: {OrderStatus.PAID, OrderStatus.RESTAURANT_ACCEPTED, OrderStatus.FAILED, OrderStatus.CANCELLED, OrderStatus.COMPLETED},
    OrderStatus.PAID: {OrderStatus.RESTAURANT_ACCEPTED, OrderStatus.REJECTED, OrderStatus.REFUNDED, OrderStatus.COMPLETED},
    OrderStatus.RESTAURANT_ACCEPTED: {OrderStatus.QUEUED, OrderStatus.CANCELLED, OrderStatus.COMPLETED},
    OrderStatus.QUEUED: {OrderStatus.PREPARING, OrderStatus.CANCELLED, OrderStatus.COMPLETED},
    OrderStatus.PREPARING: {OrderStatus.QUALITY_CHECK, OrderStatus.CANCELLED, OrderStatus.COMPLETED},
    OrderStatus.QUALITY_CHECK: {OrderStatus.READY, OrderStatus.PREPARING, OrderStatus.COMPLETED},
    OrderStatus.READY: {OrderStatus.SERVED, OrderStatus.PREPARING, OrderStatus.COMPLETED},
    OrderStatus.SERVED: {OrderStatus.COMPLETED},
    OrderStatus.COMPLETED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.FAILED: {OrderStatus.PAYMENT_PENDING},
    OrderStatus.REFUNDED: set(),
}


class InvalidTransition(Exception):
    pass


def _new_order_code() -> str:
    return f"ORB-{random.randint(10000, 99999)}"


async def create_order(db: AsyncSession, branch_id: str, table_id: str, items: list[dict], notes: str = "") -> Order:
    """items: [{menu_item_id, quantity, customizations}]"""
    menu_ids = [i["menu_item_id"] for i in items]
    result = await db.execute(select(MenuItem).where(MenuItem.id.in_(menu_ids)))
    menu_items = {m.id: m for m in result.scalars().all()}

    order = Order(id=uid(), code=_new_order_code(), branch_id=branch_id, table_id=table_id, notes=notes,
                  status=OrderStatus.CREATED)
    total = 0.0
    order_items = []
    for i in items:
        mi = menu_items[i["menu_item_id"]]
        qty = i.get("quantity", 1)
        oi = OrderItem(
            id=uid(), order_id=order.id, menu_item_id=mi.id, name_snapshot=mi.name,
            quantity=qty, unit_price=mi.price, customizations=i.get("customizations", ""),
        )
        order_items.append(oi)
        total += mi.price * qty
    order.total_amount = total

    table = await db.get(RestaurantTable, table_id)
    if table:
        table.status = TableStatus.ORDERING

    db.add(order)
    db.add_all(order_items)  # order_id FK already set on each item; no need to touch order.items
    await db.commit()
    order_id = order.id
    order = await get_order(db, order_id, populate_existing=True)

    await events.publish("OrderCreated", "order", order.id,
                          {"code": order.code, "table_id": table_id, "total_amount": total,
                           "status": order.status.value if hasattr(order.status, "value") else order.status},
                          branch_id=branch_id)
    return order


async def _route_kitchen_tasks(db: AsyncSession, order: Order):
    """Create one KitchenTask per order item, assigned to that item's station. This is the
    routing described in the spec: each dish goes only to the station responsible for it."""
    result = await db.execute(select(MenuItem).where(MenuItem.id.in_([i.menu_item_id for i in order.items])))
    menu_items = {m.id: m for m in result.scalars().all()}
    tasks = []
    for item in order.items:
        mi = menu_items[item.menu_item_id]
        task = KitchenTask(id=uid(), order_id=order.id, order_item_id=item.id, station_id=mi.station_id,
                            status=KitchenTaskStatus.QUEUED)
        tasks.append(task)
        db.add(task)
    await db.commit()

    for task in tasks:
        await events.publish("KitchenTaskAssigned", "kitchen_task", task.id,
                              {"order_id": order.id, "order_code": order.code, "station_id": task.station_id,
                               "order_item_name": next(i.name_snapshot for i in order.items if i.id == task.order_item_id),
                               "status": task.status.value},
                              branch_id=order.branch_id)
    return tasks


async def transition_order_status(db: AsyncSession, order_id: str, new_status: OrderStatus) -> Order:
    result = await db.execute(
        select(Order).options(selectinload(Order.items), selectinload(Order.tasks)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise ValueError("Order not found")

    current = OrderStatus(order.status) if not isinstance(order.status, OrderStatus) else order.status
    if new_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"Cannot transition order from {current.value} to {new_status.value}")

    order.status = new_status
    await db.commit()
    # expire_on_commit=False, items/tasks were already loaded above, and only the scalar
    # `status` column changed — no refresh needed, avoids reloading already-loaded collections.

    await events.publish("OrderStatusChanged", "order", order.id,
                          {"code": order.code, "from": current.value, "to": new_status.value},
                          branch_id=order.branch_id)

    # The moment an order is queued for the kitchen, route its items to stations.
    if new_status == OrderStatus.QUEUED:
        await _route_kitchen_tasks(db, order)

    if new_status == OrderStatus.SERVED:
        table = await db.get(RestaurantTable, order.table_id)
        if table:
            table.status = TableStatus.BILL_REQUESTED
            await db.commit()
            await events.publish("TableStatusChanged", "table", table.id,
                                  {"status": table.status.value}, branch_id=order.branch_id)

    if new_status == OrderStatus.COMPLETED:
        table = await db.get(RestaurantTable, order.table_id)
        if table:
            table.status = TableStatus.AVAILABLE   # free the table for the next customer
            await db.commit()
            await events.publish("TableReleased", "table", table.id,
                                  {"status": table.status.value}, branch_id=order.branch_id)

    return order


async def estimate_wait_seconds(db: AsyncSession, branch_id: str, items: list[dict]) -> dict:
    """Real queue-based ETA, not a guess: for each station this order touches, sum the
    avg_prep_seconds of every QUEUED/PREPARING task already ahead of it at that station,
    then add this order's own prep time at that station. The order's overall ETA is the
    max across its stations, since stations work in parallel."""
    menu_ids = [i["menu_item_id"] for i in items]
    result = await db.execute(select(MenuItem).where(MenuItem.id.in_(menu_ids)))
    menu_items = {m.id: m for m in result.scalars().all()}

    # Group this order's own items by station and sum their own prep time per station.
    own_time_by_station: dict[str, int] = {}
    for i in items:
        mi = menu_items[i["menu_item_id"]]
        own_time_by_station[mi.station_id] = own_time_by_station.get(mi.station_id, 0) + mi.avg_prep_seconds

    # Real backlog: existing active tasks at those stations, joined to their menu item's prep time.
    stations = list(own_time_by_station.keys())
    backlog_by_station: dict[str, int] = {s: 0 for s in stations}
    if stations:
        q = (
            select(KitchenTask.station_id, MenuItem.avg_prep_seconds)
            .join(Order, Order.id == KitchenTask.order_id)
            .join(OrderItem, OrderItem.id == KitchenTask.order_item_id)
            .join(MenuItem, MenuItem.id == OrderItem.menu_item_id)
            .where(Order.branch_id == branch_id)
            .where(KitchenTask.station_id.in_(stations))
            .where(KitchenTask.status.in_([KitchenTaskStatus.QUEUED, KitchenTaskStatus.ACCEPTED, KitchenTaskStatus.PREPARING]))
        )
        result = await db.execute(q)
        for station_id, prep_seconds in result.all():
            backlog_by_station[station_id] = backlog_by_station.get(station_id, 0) + prep_seconds

    per_station_eta = {s: backlog_by_station.get(s, 0) + own_time_by_station[s] for s in stations}
    overall_eta = max(per_station_eta.values()) if per_station_eta else 0
    return {"eta_seconds": overall_eta, "per_station_eta_seconds": per_station_eta}


async def add_items_to_order(db: AsyncSession, order_id: str, items: list[dict]) -> Order:
    """Appends items to an order that's already in flight (not yet SERVED/terminal).
    New items get their own kitchen tasks routed immediately if the order is already
    QUEUED or past — the kitchen sees them as fresh work with their own timer."""
    order = await get_order(db, order_id)
    if order is None:
        raise ValueError("Order not found")
    current = OrderStatus(order.status) if not isinstance(order.status, OrderStatus) else order.status
    if current in (OrderStatus.SERVED, OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED,
                   OrderStatus.FAILED, OrderStatus.REFUNDED):
        raise InvalidTransition(f"Cannot add items to an order in status {current.value}")

    menu_ids = [i["menu_item_id"] for i in items]
    result = await db.execute(select(MenuItem).where(MenuItem.id.in_(menu_ids)))
    menu_items = {m.id: m for m in result.scalars().all()}

    new_items = []
    added_total = 0.0
    for i in items:
        mi = menu_items[i["menu_item_id"]]
        qty = i.get("quantity", 1)
        oi = OrderItem(id=uid(), order_id=order.id, menu_item_id=mi.id, name_snapshot=mi.name,
                        quantity=qty, unit_price=mi.price, customizations=i.get("customizations", ""))
        new_items.append(oi)
        added_total += mi.price * qty

    order.total_amount += added_total
    db.add_all(new_items)
    await db.commit()

    order = await get_order(db, order_id, populate_existing=True)
    await events.publish("OrderItemsAdded", "order", order.id,
                          {"code": order.code, "added_total": added_total,
                           "new_items": [i.name_snapshot for i in new_items]},
                          branch_id=order.branch_id)

    # If the kitchen is already working this order, route the new items immediately too.
    if current in (OrderStatus.QUEUED, OrderStatus.PREPARING, OrderStatus.QUALITY_CHECK, OrderStatus.READY):
        tasks = []
        for item in new_items:
            mi = menu_items[item.menu_item_id]
            task = KitchenTask(id=uid(), order_id=order.id, order_item_id=item.id, station_id=mi.station_id,
                                status=KitchenTaskStatus.QUEUED)
            tasks.append(task)
            db.add(task)
        await db.commit()
        for task in tasks:
            await events.publish("KitchenTaskAssigned", "kitchen_task", task.id,
                                  {"order_id": order.id, "order_code": order.code, "station_id": task.station_id,
                                   "order_item_name": next(i.name_snapshot for i in new_items if i.id == task.order_item_id),
                                   "status": task.status.value},
                                  branch_id=order.branch_id)
        # A previously-READY order with fresh incoming items should go back to in-progress.
        if current in (OrderStatus.QUALITY_CHECK, OrderStatus.READY):
            order = await transition_order_status(db, order.id, OrderStatus.PREPARING) if current == OrderStatus.READY else order

    return await get_order(db, order_id, populate_existing=True)


async def get_order(db: AsyncSession, order_id: str, populate_existing: bool = False) -> Order | None:
    q = select(Order).options(selectinload(Order.items), selectinload(Order.tasks)).where(Order.id == order_id)
    if populate_existing:
        # Bypasses old-value diffing on relationship collections for an object already in the
        # identity map (e.g. right after we just created it), which is what makes re-hydrating
        # never-yet-loaded collections safe under the async engine.
        q = q.execution_options(populate_existing=True)
    result = await db.execute(q)
    return result.scalar_one_or_none()
