from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..database import SessionLocal
from ..models import StaffUser
from ..security import verify_password, make_staff_token, verify_staff_token, InvalidStaffToken

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(payload: LoginIn):
    async with SessionLocal() as db:
        result = await db.execute(select(StaffUser).where(StaffUser.username == payload.username))
        user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")

    token = make_staff_token(user.id, user.branch_id, user.role)
    return {"token": token, "role": user.role, "branch_id": user.branch_id, "name": user.name}


@router.get("/session")
async def session(token: str):
    """Frontend calls this to validate a stored session token on reload."""
    try:
        claims = verify_staff_token(token)
    except InvalidStaffToken as e:
        raise HTTPException(401, str(e))
    return claims
