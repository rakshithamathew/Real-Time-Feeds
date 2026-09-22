from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import get_feed_service
from app.database import get_session
from app.exceptions import FeedUnavailableError
from app.main import app

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def publish(
    client: AsyncClient, room: str, content: str, client_id: str = "A"
) -> dict[str, object]:
    response = await client.post(
        f"/api/rooms/{room}/updates",
        json={"content": content, "clientId": client_id},
    )
    assert response.status_code == 201
    return response.json()


async def test_successful_publishing(api_client: AsyncClient) -> None:
    room = f"incident-{uuid4()}"
    accepted = await publish(api_client, room, "Investigating elevated error rate", "B")

    assert accepted["roomId"] == room
    assert accepted["clientId"] == "B"
    assert accepted["content"] == "Investigating elevated error rate"
    assert isinstance(accepted["updateId"], str)
    assert isinstance(accepted["createdAt"], str)
    assert isinstance(accepted["sequence"], int)

    history = (await api_client.get(f"/api/rooms/{room}/updates")).json()
    assert history["updates"] == [accepted]


async def test_invalid_blank_content(api_client: AsyncClient) -> None:
    response = await api_client.post(
        f"/api/rooms/incident-{uuid4()}/updates",
        json={"content": " \t\n", "clientId": "A"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "traceback" not in response.text.lower()


async def test_initial_history_ordering_and_paging(api_client: AsyncClient) -> None:
    room = f"incident-{uuid4()}"
    accepted = [await publish(api_client, room, f"update {number}") for number in range(3)]

    response = await api_client.get(f"/api/rooms/{room}/updates", params={"limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert [item["sequence"] for item in body["updates"]] == [
        accepted[0]["sequence"],
        accepted[1]["sequence"],
    ]
    assert body["latestSequence"] == accepted[2]["sequence"]
    assert body["hasMore"] is True

    zero = await api_client.get(f"/api/rooms/{room}/updates", params={"after": 0, "limit": 2})
    assert zero.json() == body


async def test_replay_cursor_boundaries_and_room_isolation(api_client: AsyncClient) -> None:
    room = f"incident-{uuid4()}"
    other_room = room + "-other"
    first = await publish(api_client, room, "first")
    outsider = await publish(api_client, other_room, "outsider")
    second = await publish(api_client, room, "second")
    third = await publish(api_client, room, "third")

    replay = await api_client.get(
        f"/api/rooms/{room}/updates",
        params={"after": first["sequence"], "limit": 50},
    )
    body = replay.json()
    assert [item["sequence"] for item in body["updates"]] == [
        second["sequence"],
        third["sequence"],
    ]
    assert all(item["roomId"] == room for item in body["updates"])
    assert outsider["sequence"] not in [item["sequence"] for item in body["updates"]]
    assert body == {
        "updates": [second, third],
        "latestSequence": third["sequence"],
        "hasMore": False,
    }

    at_latest = await api_client.get(
        f"/api/rooms/{room}/updates", params={"after": third["sequence"]}
    )
    assert at_latest.json() == {
        "updates": [],
        "latestSequence": third["sequence"],
        "hasMore": False,
    }

    beyond_latest = await api_client.get(
        f"/api/rooms/{room}/updates", params={"after": int(third["sequence"]) + 1000}
    )
    assert beyond_latest.json() == at_latest.json()

    other_history = await api_client.get(f"/api/rooms/{other_room}/updates")
    assert other_history.json() == {
        "updates": [outsider],
        "latestSequence": outsider["sequence"],
        "hasMore": False,
    }


async def test_empty_room(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/rooms/incident-{uuid4()}/updates")
    assert response.json() == {"updates": [], "latestSequence": 0, "hasMore": False}


async def test_query_bounds_return_useful_validation_error(api_client: AsyncClient) -> None:
    response = await api_client.get(
        f"/api/rooms/incident-{uuid4()}/updates",
        params={"after": -1, "limit": 201},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert {detail["location"][-1] for detail in body["error"]["details"]} == {
        "after",
        "limit",
    }


async def test_persistence_failure_is_sanitized() -> None:
    class UnavailableService:
        async def publish_update(self, room_id: str, client_id: str, content: str) -> None:
            raise FeedUnavailableError

    app.dependency_overrides[get_feed_service] = UnavailableService
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/rooms/incident-001/updates",
                json={"content": "investigating", "clientId": "A"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "feed_unavailable", "message": "Incident feed unavailable"}
    }
    assert "traceback" not in response.text.lower()
