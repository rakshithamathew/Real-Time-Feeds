import pytest
from pydantic import ValidationError

from app.schemas import CreateUpdateRequest, InitialUpdatesRequest, UpdatesAfterRequest


@pytest.mark.parametrize("room", ["", " ", "\t\n", "\u2003", "x" * 129])
def test_invalid_room(room: str) -> None:
    with pytest.raises(ValidationError):
        CreateUpdateRequest(room_id=room, client_id="A", content="valid")
    with pytest.raises(ValidationError):
        InitialUpdatesRequest(room_id=room)


@pytest.mark.parametrize("content", ["", " \t\n", "\u2003", "x" * 10001])
def test_invalid_content(content: str) -> None:
    with pytest.raises(ValidationError):
        CreateUpdateRequest(room_id="room", client_id="A", content=content)


@pytest.mark.parametrize("cursor", [-1, 2**63, True, 1.5])
def test_invalid_cursor(cursor: int) -> None:
    with pytest.raises(ValidationError):
        UpdatesAfterRequest(room_id="room", after_sequence=cursor)


@pytest.mark.parametrize("limit", [0, -1, 201, True, 1.5])
def test_invalid_limit(limit: int) -> None:
    with pytest.raises(ValidationError):
        InitialUpdatesRequest(room_id="room", limit=limit)


def test_validation_boundaries() -> None:
    request = CreateUpdateRequest(room_id="x" * 128, client_id="A", content="x" * 10000)
    assert len(request.content) == 10000
    assert UpdatesAfterRequest(room_id="room", after_sequence=0, limit=1).limit == 1
    assert UpdatesAfterRequest(room_id="room", after_sequence=2**63 - 1, limit=200).limit == 200
