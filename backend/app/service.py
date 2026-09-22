import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import FeedUnavailableError
from app.realtime import RoomPublishCoordinator, UpdateBroadcaster, publish_coordinator
from app.repository import UpdateRepository
from app.schemas import UpdateResponse, UpdatesAfterRequest, UpdatesPageResponse

logger = logging.getLogger(__name__)
event_logger = logging.getLogger("uvicorn.error")


class IncidentFeedService:
    def __init__(
        self,
        session: AsyncSession,
        broadcaster: UpdateBroadcaster | None = None,
        coordinator: RoomPublishCoordinator = publish_coordinator,
    ) -> None:
        self.session = session
        self.repository = UpdateRepository(session)
        self.broadcaster = broadcaster
        self.coordinator = coordinator

    async def publish_update(self, room_id: str, client_id: str, content: str) -> UpdateResponse:
        async with self.coordinator.serialize(room_id):
            try:
                async with self.session.begin():
                    update = await self.repository.create_update(room_id, client_id, content)
                    accepted = UpdateResponse.model_validate(update)
            except SQLAlchemyError as exc:
                raise FeedUnavailableError from exc

            # Broadcast only after commit. Fan-out is transient; a client recovers
            # any missed event from PostgreSQL with its processed sequence.
            if self.broadcaster is not None:
                try:
                    await self.broadcaster.broadcast(accepted.room_id, accepted)
                except Exception:
                    logger.exception("Committed update could not be broadcast")
            event_logger.info(
                "event=incident_update_accepted room_id=%s sequence=%d",
                accepted.room_id,
                accepted.sequence,
            )
        return accepted

    async def get_updates(
        self, room_id: str, after_sequence: int = 0, limit: int = 50
    ) -> UpdatesPageResponse:
        query = UpdatesAfterRequest(
            room_id=room_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        try:
            async with self.session.begin():
                updates = await self.repository.get_updates_after(
                    query.room_id,
                    query.after_sequence,
                    query.limit,
                )
                latest_sequence = await self.repository.get_latest_sequence(query.room_id)
        except SQLAlchemyError as exc:
            raise FeedUnavailableError from exc

        last_returned = updates[-1].sequence if updates else query.after_sequence
        return UpdatesPageResponse(
            updates=[UpdateResponse.model_validate(update) for update in updates],
            latest_sequence=latest_sequence,
            has_more=last_returned < latest_sequence,
        )
