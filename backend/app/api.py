import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.realtime import RoomConnectionManager, RoomSubscription, connection_manager
from app.schemas import (
    MAX_LIMIT,
    MAX_ROOM_ID_LENGTH,
    MAX_SEQUENCE,
    PublishUpdateRequest,
    UpdateResponse,
    UpdatesPageResponse,
    WebSocketUpdateEnvelope,
)
from app.service import IncidentFeedService

router = APIRouter(prefix="/api")
websocket_router = APIRouter()
logger = logging.getLogger(__name__)
event_logger = logging.getLogger("uvicorn.error")


def get_connection_manager() -> RoomConnectionManager:
    return connection_manager


def get_feed_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    manager: Annotated[RoomConnectionManager, Depends(get_connection_manager)],
) -> IncidentFeedService:
    return IncidentFeedService(session, manager)


@router.post(
    "/rooms/{room_id}/updates",
    response_model=UpdateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_update(
    room_id: Annotated[
        str,
        Path(min_length=1, max_length=MAX_ROOM_ID_LENGTH, pattern=r".*\S.*"),
    ],
    request: PublishUpdateRequest,
    service: Annotated[IncidentFeedService, Depends(get_feed_service)],
) -> UpdateResponse:
    return await service.publish_update(room_id, request.client_id, request.content)


@router.get("/rooms/{room_id}/updates", response_model=UpdatesPageResponse)
async def get_updates(
    room_id: Annotated[
        str,
        Path(min_length=1, max_length=MAX_ROOM_ID_LENGTH, pattern=r".*\S.*"),
    ],
    service: Annotated[IncidentFeedService, Depends(get_feed_service)],
    after: Annotated[int, Query(ge=0, le=MAX_SEQUENCE)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
) -> UpdatesPageResponse:
    return await service.get_updates(room_id, after, limit)


async def send_update(websocket: WebSocket, update: UpdateResponse) -> None:
    envelope = WebSocketUpdateEnvelope(data=update)
    await websocket.send_json(envelope.model_dump(mode="json", by_alias=True))


async def send_replay(
    websocket: WebSocket,
    service: IncidentFeedService,
    room_id: str,
    after: int,
) -> int:
    cursor = after
    replayed = 0
    while True:
        page = await service.get_updates(room_id, cursor, MAX_LIMIT)
        for update in page.updates:
            await send_update(websocket, update)
            cursor = update.sequence
            replayed += 1
        if not page.has_more:
            return replayed


async def send_queued_updates(
    websocket: WebSocket,
    subscription: RoomSubscription,
) -> None:
    receive_task = asyncio.create_task(websocket.receive())
    queue_task = asyncio.create_task(subscription.queue.get())
    try:
        while True:
            done, _ = await asyncio.wait(
                {receive_task, queue_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if receive_task in done:
                message = receive_task.result()
                if message["type"] == "websocket.disconnect":
                    return
                receive_task = asyncio.create_task(websocket.receive())
            if queue_task in done:
                await send_update(websocket, queue_task.result())
                queue_task = asyncio.create_task(subscription.queue.get())
    finally:
        receive_task.cancel()
        queue_task.cancel()
        await asyncio.gather(receive_task, queue_task, return_exceptions=True)


@websocket_router.websocket("/ws/rooms/{room_id}")
async def room_updates(
    websocket: WebSocket,
    room_id: Annotated[
        str,
        Path(min_length=1, max_length=MAX_ROOM_ID_LENGTH, pattern=r".*\S.*"),
    ],
    service: Annotated[IncidentFeedService, Depends(get_feed_service)],
    manager: Annotated[RoomConnectionManager, Depends(get_connection_manager)],
    after: Annotated[int, Query(ge=0, le=MAX_SEQUENCE)] = 0,
) -> None:
    subscription = await manager.subscribe(room_id, websocket)
    event_logger.info("event=websocket_connected room_id=%s after=%d", room_id, after)
    try:
        # Registration precedes replay. Concurrent committed events enter this
        # connection's queue and are drained only after ordered replay completes.
        replayed = await send_replay(websocket, service, room_id, after)
        event_logger.info(
            "event=websocket_replay_completed room_id=%s after=%d replay_count=%d",
            room_id,
            after,
            replayed,
        )
        await send_queued_updates(websocket, subscription)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket subscription failed for room %s", room_id)
        await RoomConnectionManager.close_quietly(
            websocket,
            code=1011,
            reason="Subscription failed",
        )
    finally:
        await manager.unsubscribe(subscription)
        event_logger.info("event=websocket_disconnected room_id=%s", room_id)
