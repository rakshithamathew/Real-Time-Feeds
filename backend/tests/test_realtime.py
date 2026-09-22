from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import WebSocket

from app.realtime import RoomConnectionManager
from app.schemas import UpdateResponse


def update(room_id: str, sequence: int) -> UpdateResponse:
    return UpdateResponse(
        sequence=sequence,
        update_id=uuid4(),
        room_id=room_id,
        client_id="A",
        content=f"update {sequence}",
        created_at=datetime.now(UTC),
    )


async def test_slow_subscriber_does_not_block_other_subscribers() -> None:
    manager = RoomConnectionManager(queue_size=1)
    room = "incident-001"
    slow_socket = AsyncMock(spec=WebSocket)
    fast_socket = AsyncMock(spec=WebSocket)
    slow = await manager.subscribe(room, slow_socket)
    fast = await manager.subscribe(room, fast_socket)

    first = update(room, 1)
    await manager.broadcast(room, first)
    assert await fast.queue.get() == first

    second = update(room, 2)
    await manager.broadcast(room, second)
    assert await fast.queue.get() == second
    assert await manager.subscriber_count(room) == 1

    await manager.unsubscribe(fast)
    await manager.unsubscribe(slow)
