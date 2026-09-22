"""Create durable incident updates.

Revision ID: 0001_incident_updates
Revises: none
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_incident_updates"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "incident_updates",
        sa.Column("sequence", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("update_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("sequence"),
        sa.UniqueConstraint("update_id"),
        sa.CheckConstraint(
            "char_length(room_id) <= 128 AND room_id ~ '[^[:space:]]'",
            name="ck_incident_updates_room_id",
        ),
        sa.CheckConstraint(
            "char_length(content) <= 10000 AND content ~ '[^[:space:]]'",
            name="ck_incident_updates_content",
        ),
    )
    op.create_index(
        "ix_incident_updates_room_sequence", "incident_updates", ["room_id", "sequence"]
    )


def downgrade() -> None:
    op.drop_index("ix_incident_updates_room_sequence", table_name="incident_updates")
    op.drop_table("incident_updates")
