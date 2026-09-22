"""Persist the client that authored each update.

Revision ID: 0002_update_client_id
Revises: 0001_incident_updates
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0002_update_client_id"
down_revision: str | None = "0001_incident_updates"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "incident_updates",
        sa.Column("client_id", sa.Text(), nullable=False, server_default="A"),
    )
    op.create_check_constraint(
        "ck_incident_updates_client_id",
        "incident_updates",
        "char_length(client_id) <= 32 AND client_id ~ '[^[:space:]]'",
    )
    op.alter_column("incident_updates", "client_id", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_incident_updates_client_id",
        "incident_updates",
        type_="check",
    )
    op.drop_column("incident_updates", "client_id")
