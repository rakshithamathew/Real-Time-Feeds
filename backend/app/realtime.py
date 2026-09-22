import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from fastapi import WebSocket

from app.schemas import UpdateResponse

SUBSCRIBER_QUEUE_SIZE = 256
PUBLISH_LOCK_STRIPES = 64


class UpdateBroadcaster(Protocol):
    async def broadcast(self, room_id: str, update: UpdateResponse) -> None: ...


class RoomPublishCoordinator:
    """Serialize each room's insert-through-fan-out path in this process."""

    def __init__(self, stripes: int = PUBLISH_LOCK_STRIPES) -> None:
        self._locks = tuple(asyncio.Lock() for _ in range(stripes))

    @asynccontextmanager
    async def serialize(self, room_id: str) -> AsyncIterator[None]:
        lock = self._locks[hash(room_id) % len(self._locks)]
        async with lock:
            yield


@dataclass(eq=False, slots=True)
class RoomSubscription:
    room_id: str
    websocket: WebSocket
    queue: asyncio.Queue[UpdateResponse]


class RoomConnectionManager:
    """Transient room fan-out; PostgreSQL remains the durable event source."""

    def __init__(self, queue_size: int = SUBSCRIBER_QUEUE_SIZE) -> None:
        self._queue_size = queue_size
        self._rooms: dict[str, set[RoomSubscription]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_tasks: set[asyncio.Task[None]] = set()

    async def subscribe(self, room_id: str, websocket: WebSocket) -> RoomSubscription:
        await websocket.accept()
        subscription = RoomSubscription(
            room_id=room_id,
            websocket=websocket,
            queue=asyncio.Queue(maxsize=self._queue_size),
        )
        async with self._lock:
            self._rooms.setdefault(room_id, set()).add(subscription)
        return subscription

    async def unsubscribe(self, subscription: RoomSubscription) -> None:
        async with self._lock:
            subscribers = self._rooms.get(subscription.room_id)
            if subscribers is None:
                return
            subscribers.discard(subscription)
            if not subscribers:
                self._rooms.pop(subscription.room_id, None)

    async def broadcast(self, room_id: str, update: UpdateResponse) -> None:
        async with self._lock:
            subscribers = tuple(self._rooms.get(room_id, ()))
            overflowed: list[RoomSubscription] = []
            for subscription in subscribers:
                try:
                    subscription.queue.put_nowait(update)
                except asyncio.QueueFull:
                    overflowed.append(subscription)

            room_subscribers = self._rooms.get(room_id)
            if room_subscribers is not None:
                for subscription in overflowed:
                    room_subscribers.discard(subscription)
                if not room_subscribers:
                    self._rooms.pop(room_id, None)

        # Closing an overflowed socket is detached from publishing. The subscriber
        # was already removed, so a slow network close cannot delay other clients.
        for subscription in overflowed:
            task = asyncio.create_task(
                self.close_quietly(
                    subscription.websocket,
                    code=1013,
                    reason="Subscriber is too slow",
                )
            )
            self._cleanup_tasks.add(task)
            task.add_done_callback(self._cleanup_tasks.discard)

    async def subscriber_count(self, room_id: str) -> int:
        async with self._lock:
            return len(self._rooms.get(room_id, ()))

    @staticmethod
    async def close_quietly(websocket: WebSocket, code: int, reason: str) -> None:
        try:
            await websocket.close(code=code, reason=reason)
        except Exception:
            pass


connection_manager = RoomConnectionManager()
publish_coordinator = RoomPublishCoordinator()
