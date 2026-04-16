"""communities, events, subscriptions, favorites

Revision ID: 20260416_0012
Revises: 20260416_0011
Create Date: 2026-04-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260416_0012"
down_revision: Union[str, None] = "20260416_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "communities",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_communities_name"), "communities", ["name"], unique=False)
    op.create_index(op.f("ix_communities_created_by_user_id"), "communities", ["created_by_user_id"], unique=False)

    op.create_table(
        "community_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "community_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("communities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(length=1024), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_community_events_community_id"),
        "community_events",
        ["community_id"],
        unique=False,
    )
    op.create_index(op.f("ix_community_events_event_at"), "community_events", ["event_at"], unique=False)

    op.create_table(
        "user_community_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "community_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("communities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "community_id", name="uq_user_community_subscription"),
    )
    op.create_index(
        op.f("ix_user_community_subscriptions_user_id"),
        "user_community_subscriptions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_community_subscriptions_community_id"),
        "user_community_subscriptions",
        ["community_id"],
        unique=False,
    )

    op.create_table(
        "user_community_event_favorites",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("community_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "event_id", name="uq_user_community_event_favorite"),
    )
    op.create_index(
        op.f("ix_user_community_event_favorites_user_id"),
        "user_community_event_favorites",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_community_event_favorites_event_id"),
        "user_community_event_favorites",
        ["event_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_community_event_favorites_event_id"), table_name="user_community_event_favorites")
    op.drop_index(op.f("ix_user_community_event_favorites_user_id"), table_name="user_community_event_favorites")
    op.drop_table("user_community_event_favorites")

    op.drop_index(op.f("ix_user_community_subscriptions_community_id"), table_name="user_community_subscriptions")
    op.drop_index(op.f("ix_user_community_subscriptions_user_id"), table_name="user_community_subscriptions")
    op.drop_table("user_community_subscriptions")

    op.drop_index(op.f("ix_community_events_event_at"), table_name="community_events")
    op.drop_index(op.f("ix_community_events_community_id"), table_name="community_events")
    op.drop_table("community_events")

    op.drop_index(op.f("ix_communities_created_by_user_id"), table_name="communities")
    op.drop_index(op.f("ix_communities_name"), table_name="communities")
    op.drop_table("communities")
