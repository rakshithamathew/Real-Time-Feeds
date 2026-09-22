from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IncidentUpdate
from app.schemas import CreateUpdateRequest, InitialUpdatesRequest, UpdatesAfterRequest


class UpdateRepository:
    """One session per task. Callers own commit/rollback and publish only after commit."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_update(self, room_id: str, client_id: str, content: str) -> IncidentUpdate:
        data = CreateUpdateRequest(room_id=room_id, client_id=client_id, content=content)
        update = IncidentUpdate(
            room_id=data.room_id,
            client_id=data.client_id,
            content=data.content,
        )
        self.session.add(update)
        await self.session.flush()
        return update

    async def get_updates_after(
        self, room_id: str, after_sequence: int, limit: int = 50
    ) -> list[IncidentUpdate]:
        query = UpdatesAfterRequest(room_id=room_id, after_sequence=after_sequence, limit=limit)
        result = await self.session.scalars(
            select(IncidentUpdate)
            .where(
                IncidentUpdate.room_id == query.room_id,
                IncidentUpdate.sequence > query.after_sequence,
            )
            .order_by(IncidentUpdate.sequence.asc())
            .limit(query.limit)
        )
        return list(result)

    async def get_initial_updates(self, room_id: str, limit: int = 50) -> list[IncidentUpdate]:
        query = InitialUpdatesRequest(room_id=room_id, limit=limit)
        # Select the newest N first, then return that window in ascending order.
        newest = (
            select(IncidentUpdate.sequence)
            .where(IncidentUpdate.room_id == query.room_id)
            .order_by(IncidentUpdate.sequence.desc())
            .limit(query.limit)
        )
        result = await self.session.scalars(
            select(IncidentUpdate)
            .where(
                IncidentUpdate.room_id == query.room_id,
                IncidentUpdate.sequence.in_(newest),
            )
            .order_by(IncidentUpdate.sequence.asc())
        )
        return list(result)

    async def get_latest_sequence(self, room_id: str) -> int:
        query = InitialUpdatesRequest(room_id=room_id, limit=1)
        latest = await self.session.scalar(
            select(func.max(IncidentUpdate.sequence)).where(IncidentUpdate.room_id == query.room_id)
        )
        return latest or 0
