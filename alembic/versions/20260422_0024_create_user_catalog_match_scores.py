"""create user catalog match scores table

Revision ID: 20260422_0024
Revises: 20260422_0023
Create Date: 2026-04-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260422_0024"
down_revision: Union[str, None] = "20260422_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("user_catalog_match_scores"):
        return

    op.create_table(
        "user_catalog_match_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("catalog_type", sa.String(length=32), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("profile_text", sa.Text(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "catalog_type",
            "item_id",
            name="uq_user_catalog_match_scores_user_type_item",
        ),
    )
    op.create_index(op.f("ix_user_catalog_match_scores_catalog_type"), "user_catalog_match_scores", ["catalog_type"], unique=False)
    op.create_index(op.f("ix_user_catalog_match_scores_item_id"), "user_catalog_match_scores", ["item_id"], unique=False)
    op.create_index(op.f("ix_user_catalog_match_scores_user_id"), "user_catalog_match_scores", ["user_id"], unique=False)


def downgrade() -> None:
    if not _has_table("user_catalog_match_scores"):
        return

    op.drop_index(op.f("ix_user_catalog_match_scores_user_id"), table_name="user_catalog_match_scores")
    op.drop_index(op.f("ix_user_catalog_match_scores_item_id"), table_name="user_catalog_match_scores")
    op.drop_index(op.f("ix_user_catalog_match_scores_catalog_type"), table_name="user_catalog_match_scores")
    op.drop_table("user_catalog_match_scores")
