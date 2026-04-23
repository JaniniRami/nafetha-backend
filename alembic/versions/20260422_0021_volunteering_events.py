"""create volunteering events table

Revision ID: 20260422_0021
Revises: 20260422_0020
Create Date: 2026-04-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260422_0021"
down_revision: Union[str, None] = "20260422_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "volunteering_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_url", sa.String(length=1024), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("subtitle", sa.String(length=512), nullable=True),
        sa.Column("organizer", sa.String(length=512), nullable=True),
        sa.Column("organizer_website", sa.String(length=1024), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_dates", sa.String(length=255), nullable=True),
        sa.Column("days", sa.String(length=512), nullable=True),
        sa.Column("keywords", sa.String(length=1024), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_volunteering_events_event_url"), "volunteering_events", ["event_url"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_volunteering_events_event_url"), table_name="volunteering_events")
    op.drop_table("volunteering_events")
