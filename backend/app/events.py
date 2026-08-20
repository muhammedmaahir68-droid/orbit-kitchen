"""
Domain event bus.

Implemented as an in-process asyncio pub/sub for this vertical slice, but every
publisher/subscriber uses this module as the seam — swapping the body of `publish`
and `subscribe` for Redis Pub/Sub (or Kafka later) requires no changes anywhere else
in the codebase. Every published event is also durably written to EventLog so the
activity stream and audit trail are backed by real rows, not in-memory state.
"""
import asyncio
import json
from datetime import datetime
from typing import Callable, Awaitable

from sqlalchemy import select
from .database import SessionLocal
from .models import EventLog, uid

Handler = Callable[[dict], Awaitable[None]]

_subscribers: list[Handler] = []


def subscribe(handler: Handler) -> None:
    _subscribers.append(handler)


async def publish(event_type: str, entity_type: str, entity_id: str, payload: dict, branch_id: str | None = None) -> None:
    event = {
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "branch_id": branch_id,
        "payload": payload,
        "created_at": datetime.utcnow().isoformat(),
    }

    # Durable write first — the event log is the source of truth for the activity stream.
    async with SessionLocal() as session:
        session.add(EventLog(
            id=uid(),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            branch_id=branch_id,
            payload=payload,
        ))
        await session.commit()

    # Then fan out to all live subscribers (WebSocket manager, future notification service, etc.)
    await asyncio.gather(*(h(event) for h in _subscribers), return_exceptions=True)
