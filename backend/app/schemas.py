from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field

MAX_CONTENT_LENGTH = 10_000
MAX_ROOM_ID_LENGTH = 128
MAX_CLIENT_ID_LENGTH = 32
MAX_LIMIT = 200
MAX_SEQUENCE = 2**63 - 1


def reject_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("Must not be blank or whitespace-only")
    # Preserve exact identifiers and content; never silently merge room names.
    return value


RoomId = Annotated[
    str, Field(min_length=1, max_length=MAX_ROOM_ID_LENGTH), AfterValidator(reject_blank)
]
Content = Annotated[
    str, Field(min_length=1, max_length=MAX_CONTENT_LENGTH), AfterValidator(reject_blank)
]
ClientId = Annotated[
    str, Field(min_length=1, max_length=MAX_CLIENT_ID_LENGTH), AfterValidator(reject_blank)
]
Cursor = Annotated[int, Field(strict=True, ge=0, le=MAX_SEQUENCE)]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=MAX_LIMIT)]


class CreateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: RoomId
    client_id: ClientId
    content: Content


class PublishUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: ClientId = Field(alias="clientId")
    content: Content


class InitialUpdatesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: RoomId
    limit: PageLimit = 50


class UpdatesAfterRequest(InitialUpdatesRequest):
    after_sequence: Cursor = 0


class UpdateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence: Annotated[int, Field(gt=0)]
    update_id: UUID = Field(serialization_alias="updateId")
    room_id: RoomId = Field(serialization_alias="roomId")
    client_id: ClientId = Field(serialization_alias="clientId")
    content: Content
    created_at: AwareDatetime = Field(serialization_alias="createdAt")


class UpdatesPageResponse(BaseModel):
    updates: list[UpdateResponse]
    latest_sequence: Cursor = Field(serialization_alias="latestSequence")
    has_more: bool = Field(serialization_alias="hasMore")


class WebSocketUpdateEnvelope(BaseModel):
    type: Literal["update"] = "update"
    data: UpdateResponse
