import os
import time
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.realtime import connection_manager

pytestmark = pytest.mark.integration


@pytest.fixture
def client() -> Iterator[TestClient]:
    if os.getenv("RUN_DB_TESTS") != "1":
        pytest.skip("Set RUN_DB_TESTS=1 and migrate TEST_DATABASE_URL first")
    with TestClient(app) as test_client:
        yield test_client


def publish(client: TestClient, room: str, content: str, client_id: str = "A") -> dict[str, object]:
    response = client.post(
        f"/api/rooms/{room}/updates",
        json={"content": content, "clientId": client_id},
    )
    assert response.status_code == 201
    return response.json()


def receive_update(websocket: object) -> dict[str, object]:
    message = websocket.receive_json()  # type: ignore[attr-defined]
    assert message["type"] == "update"
    return message["data"]


def test_rest_publish_reaches_another_live_client_in_the_same_room(client: TestClient) -> None:
    room = f"ws-{uuid4()}"
    with (
        client.websocket_connect(f"/ws/rooms/{room}?after=0") as client_a,
        client.websocket_connect(f"/ws/rooms/{room}?after=0") as client_b,
    ):
        accepted = publish(client, room, "live update", "B")
        assert accepted["clientId"] == "B"
        assert receive_update(client_a) == accepted
        assert receive_update(client_b) == accepted


def test_replay_returns_updates_strictly_after_cursor(client: TestClient) -> None:
    room = f"ws-{uuid4()}"
    first = publish(client, room, "first")
    second = publish(client, room, "second")
    third = publish(client, room, "third")

    with client.websocket_connect(f"/ws/rooms/{room}?after={first['sequence']}") as websocket:
        assert receive_update(websocket) == second
        assert receive_update(websocket) == third


def test_disconnect_gap_and_reconnect_replays_every_missed_update(client: TestClient) -> None:
    room = f"ws-{uuid4()}"
    with client.websocket_connect(f"/ws/rooms/{room}?after=0") as client_b:
        before_gap = publish(client, room, "before gap")
        assert receive_update(client_b) == before_gap
        recorded_cursor = before_gap["sequence"]

    missed = [
        publish(client, room, "missed one"),
        publish(client, room, "missed two"),
        publish(client, room, "missed three"),
    ]

    with client.websocket_connect(
        f"/ws/rooms/{room}?after={recorded_cursor}"
    ) as reconnected_client_b:
        replayed = [receive_update(reconnected_client_b) for _ in missed]

    assert replayed == missed
    assert [update["sequence"] for update in replayed] == sorted(
        update["sequence"] for update in missed
    )


def test_rooms_never_receive_each_others_events(client: TestClient) -> None:
    first_room = f"ws-{uuid4()}"
    second_room = f"ws-{uuid4()}"
    with (
        client.websocket_connect(f"/ws/rooms/{first_room}?after=0") as first_socket,
        client.websocket_connect(f"/ws/rooms/{second_room}?after=0") as second_socket,
    ):
        first_update = publish(client, first_room, "first room only")
        assert receive_update(first_socket) == first_update

        second_update = publish(client, second_room, "second room only")
        assert receive_update(second_socket) == second_update


def test_disconnected_subscriber_is_removed(client: TestClient) -> None:
    room = f"ws-{uuid4()}"
    with client.websocket_connect(f"/ws/rooms/{room}?after=0"):
        assert client.portal.call(connection_manager.subscriber_count, room) == 1

    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if client.portal.call(connection_manager.subscriber_count, room) == 0:
            break
        time.sleep(0.01)
    assert client.portal.call(connection_manager.subscriber_count, room) == 0
