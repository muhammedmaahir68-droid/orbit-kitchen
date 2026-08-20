from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..database import SessionLocal
from ..models import RestaurantTable, Branch
from ..security import make_table_token, verify_table_token, InvalidTableToken

router = APIRouter(prefix="/api/v1/tables", tags=["tables"])


@router.get("/resolve")
async def resolve_table(token: str):
    """The consumer web app calls this the moment it loads, with the token from the QR URL.
    This is the ONLY way the app learns which table it's ordering for — never a client-typed
    or URL-editable raw table_id."""
    try:
        branch_id, table_id = verify_table_token(token)
    except InvalidTableToken as e:
        raise HTTPException(400, str(e))

    async with SessionLocal() as db:
        table = await db.get(RestaurantTable, table_id)
        if table is None or table.branch_id != branch_id:
            raise HTTPException(404, "Table not found")
        branch = await db.get(Branch, branch_id)

    return {
        "branch_id": branch_id,
        "table_id": table_id,
        "table_number": table.number,
        "branch_name": branch.name if branch else None,
    }


@router.get("/{table_id}/qr-token")
async def get_qr_token(table_id: str):
    """Admin/setup-time endpoint: generates the token to embed in that table's printed QR code."""
    async with SessionLocal() as db:
        table = await db.get(RestaurantTable, table_id)
        if table is None:
            raise HTTPException(404, "Table not found")
    token = make_table_token(table.branch_id, table_id)
    return {"table_id": table_id, "table_number": table.number, "token": token}


@router.get("")
async def list_tables(branch_id: str):
    async with SessionLocal() as db:
        result = await db.execute(select(RestaurantTable).where(RestaurantTable.branch_id == branch_id))
        tables = result.scalars().all()
    return [
        {"id": t.id, "number": t.number, "status": t.status.value if hasattr(t.status, "value") else t.status,
         "token": make_table_token(t.branch_id, t.id)}
        for t in tables
    ]
