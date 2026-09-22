from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repository import UpdateRepository
from app.schemas import MAX_CONTENT_LENGTH, UpdateResponse

pytestmark = pytest.mark.integration


async def test_ordering_cursor_and_room_isolation(db_session: AsyncSession) -> None:
    repo = UpdateRepository(db_session)
    room = str(uuid4())
    other = room + " "
    first = await repo.create_update(room, "A", "first")
    outsider = await repo.create_update(other, "B", "other room")
    second = await repo.create_update(room, "B", "second")
    third = await repo.create_update(room, "A", "third")

    assert first.sequence < outsider.sequence < second.sequence < third.sequence
    assert [u.sequence for u in await repo.get_updates_after(room, 0, 200)] == [
        first.sequence,
        second.sequence,
        third.sequence,
    ]
    assert [u.sequence for u in await repo.get_updates_after(room, first.sequence, 1)] == [
        second.sequence
    ]
    assert [u.sequence for u in await repo.get_updates_after(room, outsider.sequence, 200)] == [
        second.sequence,
        third.sequence,
    ]
    assert await repo.get_updates_after(room, third.sequence, 200) == []
    assert await repo.get_updates_after(room, third.sequence + 1000, 200) == []
    assert await repo.get_updates_after(str(uuid4()), 0, 200) == []
    assert [u.sequence for u in await repo.get_initial_updates(room, 2)] == [
        second.sequence,
        third.sequence,
    ]
    assert [u.sequence for u in await repo.get_initial_updates(other, 200)] == [outsider.sequence]
    assert await repo.get_initial_updates(str(uuid4()), 200) == []
    # now() is transaction-scoped: equal timestamps must not affect ordering.
    assert first.created_at == second.created_at == third.created_at


async def test_generated_fields_and_caller_transaction(db_session: AsyncSession) -> None:
    repo = UpdateRepository(db_session)
    room = str(uuid4())
    update = await repo.create_update(room, "B", "  preserve content  ")
    response = UpdateResponse.model_validate(update)
    assert response.update_id.version == 4
    assert response.created_at.utcoffset() is not None
    assert response.sequence > 0
    assert response.client_id == "B"
    assert response.content == "  preserve content  "
    await db_session.commit()
    db_session.expunge_all()
    stored = await repo.get_initial_updates(room, 1)
    assert stored[0].update_id == response.update_id
    assert stored[0].created_at == response.created_at
    await repo.create_update(room, "A", "rolled back")
    await db_session.rollback()
    assert len(await repo.get_initial_updates(room, 200)) == 1


@pytest.mark.parametrize(
    "room,content",
    [("", "ok"), ("\t \n", "ok"), ("ok", "\n\t"), ("ok", "x" * (MAX_CONTENT_LENGTH + 1))],
)
async def test_repository_rejects_invalid_writes(
    db_session: AsyncSession, room: str, content: str
) -> None:
    with pytest.raises(ValidationError):
        await UpdateRepository(db_session).create_update(room, "A", content)


@pytest.mark.parametrize("cursor,limit", [(-1, 1), (0, 0), (0, 201)])
async def test_repository_rejects_invalid_queries(
    db_session: AsyncSession, cursor: int, limit: int
) -> None:
    with pytest.raises(ValidationError):
        await UpdateRepository(db_session).get_updates_after("room", cursor, limit)


@pytest.mark.parametrize(
    "room,content", [("", "ok"), ("\n\t", "ok"), ("ok", " "), ("ok", "x" * 10001)]
)
async def test_database_rejects_invalid_direct_inserts(
    db_session: AsyncSession, room: str, content: str
) -> None:
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO incident_updates (update_id, room_id, client_id, content) "
                    "VALUES (:id, :room, 'A', :content)"
                ),
                {"id": uuid4(), "room": room, "content": content},
            )


async def test_database_rejects_duplicate_uuid(db_session: AsyncSession) -> None:
    update = await UpdateRepository(db_session).create_update(str(uuid4()), "A", "first")
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO incident_updates (update_id, room_id, client_id, content) "
                    "VALUES (:id, 'different room', 'B', 'duplicate')"
                ),
                {"id": update.update_id},
            )
