from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IncidentUpdate(Base):
    __tablename__ = "incident_updates"
    __table_args__ = (
        CheckConstraint(
            "char_length(room_id) <= 128 AND room_id ~ '[^[:space:]]'",
            name="ck_incident_updates_room_id",
        ),
        CheckConstraint(
            "char_length(content) <= 10000 AND content ~ '[^[:space:]]'",
            name="ck_incident_updates_content",
        ),
        CheckConstraint(
            "char_length(client_id) <= 32 AND client_id ~ '[^[:space:]]'",
            name="ck_incident_updates_client_id",
        ),
        Index("ix_incident_updates_room_sequence", "room_id", "sequence"),
    )

    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    update_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), default=uuid4, unique=True)
    room_id: Mapped[str] = mapped_column(Text)
    client_id: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
