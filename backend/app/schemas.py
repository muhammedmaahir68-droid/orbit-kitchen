from pydantic import BaseModel
from typing import Optional


class OrderItemIn(BaseModel):
    menu_item_id: str
    quantity: int = 1
    customizations: str = ""


class OrderCreateIn(BaseModel):
    table_token: str
    items: list[OrderItemIn]
    notes: str = ""


class AddItemsIn(BaseModel):
    items: list[OrderItemIn]


class OrderStatusIn(BaseModel):
    status: str


class TaskStatusIn(BaseModel):
    status: str
