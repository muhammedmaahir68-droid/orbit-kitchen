from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import KitchenTask, Order, KitchenTaskStatus, OrderStatus
from .. import events
from . import order_service


class InvalidTaskTransition(Exception):
    pass


TASK_TRANSITIONS = {
    KitchenTaskStatus.QUEUED: {KitchenTaskStatus.ACCEPTED},
    KitchenTaskStatus.ACCEPTED: {KitchenTaskStatus.PREPARING},
    KitchenTaskStatus.PREPARING: {KitchenTaskStatus.READY},
    KitchenTaskStatus.READY: set(),
}


async def list_tasks_for_branch(db: AsyncSession, branch_id: str, station_id: str | None = None):
    q = (
        select(KitchenTask)
        .join(Order, Order.id == KitchenTask.order_id)
        .options(selectinload(KitchenTask.order).selectinload(Order.items))
        .where(Order.branch_id == branch_id)
        .where(KitchenTask.status != KitchenTaskStatus.READY)
    )
    if station_id:
        q = q.where(KitchenTask.station_id == station_id)
    result = await db.execute(q.order_by(KitchenTask.created_at))
    return result.scalars().all()


async def update_task_status(db: AsyncSession, task_id: str, new_status: KitchenTaskStatus) -> KitchenTask:
    task = await db.get(KitchenTask, task_id)
    if task is None:
        raise ValueError("Kitchen task not found")

    current = KitchenTaskStatus(task.status) if not isinstance(task.status, KitchenTaskStatus) else task.status
    if new_status not in TASK_TRANSITIONS.get(current, set()):
        raise InvalidTaskTransition(f"Cannot transition task from {current.value} to {new_status.value}")

    task.status = new_status
    await db.commit()
    await db.refresh(task)

    order = await db.get(Order, task.order_id)

    await events.publish("KitchenTaskStatusChanged", "kitchen_task", task.id,
                          {"order_id": task.order_id, "order_code": order.code if order else None,
                           "station_id": task.station_id, "from": current.value, "to": new_status.value},
                          branch_id=order.branch_id if order else None)

    # Auto-drive the order state machine off real task state, never off a timer or a guess.
    if order is not None:
        await _sync_order_status_from_tasks(db, order.id)

    return task


async def _sync_order_status_from_tasks(db: AsyncSession, order_id: str):
    result = await db.execute(select(KitchenTask).where(KitchenTask.order_id == order_id))
    tasks = result.scalars().all()
    if not tasks:
        return

    statuses = {KitchenTaskStatus(t.status) if not isinstance(t.status, KitchenTaskStatus) else t.status for t in tasks}
    order = await db.get(Order, order_id)
    current = OrderStatus(order.status) if not isinstance(order.status, OrderStatus) else order.status

    if statuses == {KitchenTaskStatus.READY} and current == OrderStatus.QUALITY_CHECK:
        await order_service.transition_order_status(db, order_id, OrderStatus.READY)
    elif KitchenTaskStatus.PREPARING in statuses and current == OrderStatus.QUEUED:
        await order_service.transition_order_status(db, order_id, OrderStatus.PREPARING)
    elif statuses == {KitchenTaskStatus.READY} and current == OrderStatus.PREPARING:
        # all stations finished without an explicit quality-check step in between
        await order_service.transition_order_status(db, order_id, OrderStatus.QUALITY_CHECK)
        await order_service.transition_order_status(db, order_id, OrderStatus.READY)
