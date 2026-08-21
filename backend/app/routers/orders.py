from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas import OrderCreateIn, OrderStatusIn, AddItemsIn
from ..services import order_service
from ..models import OrderStatus
from ..security import verify_table_token, InvalidTableToken

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


def _serialize(order):
    return {
        "id": order.id,
        "code": order.code,
        "branch_id": order.branch_id,
        "table_id": order.table_id,
        "status": order.status.value if hasattr(order.status, "value") else order.status,
        "total_amount": order.total_amount,
        "notes": order.notes,
        "items": [
            {"id": i.id, "name": i.name_snapshot, "quantity": i.quantity, "unit_price": i.unit_price,
             "customizations": i.customizations}
            for i in order.items
        ],
        "tasks": [
            {"id": t.id, "station_id": t.station_id,
             "status": t.status.value if hasattr(t.status, "value") else t.status}
            for t in order.tasks
        ],
    }


@router.get("")
async def list_orders(branch_id: str, db: AsyncSession = Depends(get_db)):
    """Active orders for a branch — used by the cashier/manager dashboard on load."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from ..models import Order
    terminal = [OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED,
                OrderStatus.FAILED, OrderStatus.REFUNDED]
    result = await db.execute(
        select(Order).options(selectinload(Order.items), selectinload(Order.tasks))
        .where(Order.branch_id == branch_id, Order.status.not_in(terminal))
        .order_by(Order.created_at.desc())
    )
    return [_serialize(o) for o in result.scalars().all()]


@router.post("/estimate")
async def estimate(payload: OrderCreateIn, db: AsyncSession = Depends(get_db)):
    """Real queue-based ETA shown to the customer before they confirm the order."""
    try:
        branch_id, table_id = verify_table_token(payload.table_token)
    except InvalidTableToken as e:
        raise HTTPException(400, str(e))
    result = await order_service.estimate_wait_seconds(db, branch_id, [i.model_dump() for i in payload.items])
    return result


@router.post("")
async def create_order(payload: OrderCreateIn, db: AsyncSession = Depends(get_db)):
    try:
        branch_id, table_id = verify_table_token(payload.table_token)
    except InvalidTableToken as e:
        raise HTTPException(400, str(e))
    order = await order_service.create_order(
        db, branch_id, table_id, [i.model_dump() for i in payload.items], payload.notes,
    )
    return _serialize(order)


@router.get("/{order_id}")
async def get_order(order_id: str, db: AsyncSession = Depends(get_db)):
    order = await order_service.get_order(db, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    return _serialize(order)


@router.patch("/{order_id}/status")
async def update_order_status(order_id: str, payload: OrderStatusIn, db: AsyncSession = Depends(get_db)):
    try:
        new_status = OrderStatus(payload.status)
    except ValueError:
        raise HTTPException(422, f"Unknown status '{payload.status}'")
    try:
        order = await order_service.transition_order_status(db, order_id, new_status)
    except order_service.InvalidTransition as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _serialize(order)


@router.post("/{order_id}/items")
async def add_items(order_id: str, payload: AddItemsIn, db: AsyncSession = Depends(get_db)):
    """Customer taps 'add more items' mid-meal — appends to the same open order."""
    try:
        order = await order_service.add_items_to_order(db, order_id, [i.model_dump() for i in payload.items])
    except order_service.InvalidTransition as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _serialize(order)


@router.get("/revenue/summary")
async def revenue_summary(branch_id: str, db: AsyncSession = Depends(get_db)):
    """Real-time revenue breakdown for the cashier dashboard. Excludes CANCELLED/REJECTED orders."""
    from sqlalchemy import select, func
    from ..models import Order
    from datetime import datetime, timedelta, timezone

    exclude = [OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.REFUNDED, OrderStatus.FAILED]

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)
    year_start = today_start.replace(month=1, day=1)

    async def _total(since=None):
        q = select(func.coalesce(func.sum(Order.total_amount), 0.0)).where(
            Order.branch_id == branch_id,
            Order.status.not_in(exclude),
        )
        if since:
            q = q.where(Order.created_at >= since)
        result = await db.execute(q)
        return float(result.scalar())

    async def _count(since=None):
        q = select(func.count(Order.id)).where(
            Order.branch_id == branch_id,
            Order.status.not_in(exclude),
        )
        if since:
            q = q.where(Order.created_at >= since)
        result = await db.execute(q)
        return int(result.scalar())

    # Last 7 days for the bar chart
    daily = []
    for i in range(6, -1, -1):
        day_s = today_start - timedelta(days=i)
        day_e = day_s + timedelta(days=1)
        q = select(func.coalesce(func.sum(Order.total_amount), 0.0)).where(
            Order.branch_id == branch_id,
            Order.status.not_in(exclude),
            Order.created_at >= day_s,
            Order.created_at < day_e,
        )
        result = await db.execute(q)
        daily.append({"date": day_s.strftime("%a %d"), "revenue": float(result.scalar())})

    return {
        "today": await _total(today_start),
        "week": await _total(week_start),
        "month": await _total(month_start),
        "year": await _total(year_start),
        "total": await _total(),
        "today_orders": await _count(today_start),
        "total_orders": await _count(),
        "daily_chart": daily,
        "server_time": now.isoformat(),
    }
