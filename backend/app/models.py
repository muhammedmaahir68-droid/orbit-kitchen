import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Integer, Float, ForeignKey, DateTime, Enum, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def uid() -> str:
    return str(uuid.uuid4())


class OrderStatus(str, enum.Enum):
    CREATED = "CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"
    RESTAURANT_ACCEPTED = "RESTAURANT_ACCEPTED"
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    QUALITY_CHECK = "QUALITY_CHECK"
    READY = "READY"
    SERVED = "SERVED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class KitchenTaskStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    ACCEPTED = "ACCEPTED"
    PREPARING = "PREPARING"
    READY = "READY"


class TableStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    OCCUPIED = "OCCUPIED"
    ORDERING = "ORDERING"
    PREPARING = "PREPARING"
    DINING = "DINING"
    BILL_REQUESTED = "BILL_REQUESTED"
    CLEANING = "CLEANING"


class Restaurant(Base):
    __tablename__ = "restaurants"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    branches: Mapped[list["Branch"]] = relationship(back_populates="restaurant")


class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    restaurant_id: Mapped[str] = mapped_column(ForeignKey("restaurants.id"))
    name: Mapped[str] = mapped_column(String)
    upi_id: Mapped[str] = mapped_column(String, default="")   # cashier-configurable UPI VPA
    restaurant: Mapped["Restaurant"] = relationship(back_populates="branches")
    tables: Mapped[list["RestaurantTable"]] = relationship(back_populates="branch")
    stations: Mapped[list["KitchenStation"]] = relationship(back_populates="branch")


class RestaurantTable(Base):
    __tablename__ = "tables"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    number: Mapped[int] = mapped_column(Integer)
    capacity: Mapped[int] = mapped_column(Integer, default=4)
    status: Mapped[str] = mapped_column(Enum(TableStatus), default=TableStatus.AVAILABLE)
    branch: Mapped["Branch"] = relationship(back_populates="tables")


class KitchenStation(Base):
    __tablename__ = "kitchen_stations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String)  # e.g. Main Kitchen, Fry Station, Beverage, Dessert
    branch: Mapped["Branch"] = relationship(back_populates="stations")


class MenuCategory(Base):
    __tablename__ = "menu_categories"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String)


class MenuItem(Base):
    __tablename__ = "menu_items"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    category_id: Mapped[str] = mapped_column(ForeignKey("menu_categories.id"))
    station_id: Mapped[str] = mapped_column(ForeignKey("kitchen_stations.id"))
    name: Mapped[str] = mapped_column(String)
    price: Mapped[float] = mapped_column(Float)
    avg_prep_seconds: Mapped[int] = mapped_column(Integer, default=600)
    is_available: Mapped[bool] = mapped_column(default=True)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String, unique=True)  # ORB-10482 style
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    table_id: Mapped[str] = mapped_column(ForeignKey("tables.id"))
    status: Mapped[str] = mapped_column(Enum(OrderStatus), default=OrderStatus.CREATED)
    notes: Mapped[str] = mapped_column(Text, default="")
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    tasks: Mapped[list["KitchenTask"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    menu_item_id: Mapped[str] = mapped_column(ForeignKey("menu_items.id"))
    name_snapshot: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float)
    customizations: Mapped[str] = mapped_column(Text, default="")
    order: Mapped["Order"] = relationship(back_populates="items")


class KitchenTask(Base):
    """One kitchen task per order item, routed to a station. This is what the KDS renders."""
    __tablename__ = "kitchen_tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    order_item_id: Mapped[str] = mapped_column(ForeignKey("order_items.id"))
    station_id: Mapped[str] = mapped_column(ForeignKey("kitchen_stations.id"))
    status: Mapped[str] = mapped_column(Enum(KitchenTaskStatus), default=KitchenTaskStatus.QUEUED)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    order: Mapped["Order"] = relationship(back_populates="tasks")


class StaffUser(Base):
    __tablename__ = "staff_users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"))
    username: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)  # KITCHEN, CASHIER, MANAGER


class EventLog(Base):
    """Append-only domain event log. Every state transition in the system writes here."""
    __tablename__ = "event_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    event_type: Mapped[str] = mapped_column(String)
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String)
    branch_id: Mapped[str] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
