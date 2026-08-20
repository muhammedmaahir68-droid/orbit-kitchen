from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ..database import get_db
from ..schemas import TaskStatusIn
from ..services import kitchen_service
from ..models import KitchenTaskStatus

router = APIRouter(prefix="/api/v1/kitchen", tags=["kitchen"])


@router.get("/tasks")
async def list_tasks(branch_id: str, station_id: str | None = None, db: AsyncSession = Depends(get_db)):
    tasks = await kitchen_service.list_tasks_for_branch(db, branch_id, station_id)
    now = datetime.utcnow()
    return [
        {
            "id": t.id,
            "order_id": t.order_id,
            "order_code": t.order.code,
            "table_id": t.order.table_id,
            "station_id": t.station_id,
            "status": t.status.value if hasattr(t.status, "value") else t.status,
            "item_name": next((i.name_snapshot for i in t.order.items if i.id == t.order_item_id), None),
            "elapsed_seconds": int((now - t.created_at).total_seconds()),
        }
        for t in tasks
    ]


@router.patch("/tasks/{task_id}/status")
async def update_task_status(task_id: str, payload: TaskStatusIn, db: AsyncSession = Depends(get_db)):
    try:
        new_status = KitchenTaskStatus(payload.status)
    except ValueError:
        raise HTTPException(422, f"Unknown status '{payload.status}'")
    try:
        task = await kitchen_service.update_task_status(db, task_id, new_status)
    except kitchen_service.InvalidTaskTransition as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"id": task.id, "status": task.status.value if hasattr(task.status, "value") else task.status}
