"""create user roadmaps and steps tables

Revision ID: 20260423_0028
Revises: 20260423_0027
Create Date: 2026-04-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260423_0028"
down_revision: Union[str, None] = "20260423_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _has_table("user_roadmaps"):
        op.create_table(
            "user_roadmaps",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("goal_skill", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_user_roadmaps_goal_skill"), "user_roadmaps", ["goal_skill"], unique=False)
        op.create_index(op.f("ix_user_roadmaps_user_id"), "user_roadmaps", ["user_id"], unique=False)
        op.create_index(op.f("ix_user_roadmaps_user_profile_id"), "user_roadmaps", ["user_profile_id"], unique=False)

    if not _has_table("user_roadmap_steps"):
        op.create_table(
            "user_roadmap_steps",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("roadmap_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("step_order", sa.Integer(), nullable=False),
            sa.Column("main", sa.String(length=255), nullable=False),
            sa.Column("technical_complement", sa.String(length=255), nullable=False),
            sa.Column("tool_or_soft_skill", sa.String(length=255), nullable=False),
            sa.Column("completed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["roadmap_id"], ["user_roadmaps.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("roadmap_id", "step_order", name="uq_user_roadmap_steps_roadmap_order"),
        )
        op.create_index(op.f("ix_user_roadmap_steps_roadmap_id"), "user_roadmap_steps", ["roadmap_id"], unique=False)


def downgrade() -> None:
    if _has_table("user_roadmap_steps"):
        op.drop_index(op.f("ix_user_roadmap_steps_roadmap_id"), table_name="user_roadmap_steps")
        op.drop_table("user_roadmap_steps")

    if _has_table("user_roadmaps"):
        op.drop_index(op.f("ix_user_roadmaps_user_profile_id"), table_name="user_roadmaps")
        op.drop_index(op.f("ix_user_roadmaps_user_id"), table_name="user_roadmaps")
        op.drop_index(op.f("ix_user_roadmaps_goal_skill"), table_name="user_roadmaps")
        op.drop_table("user_roadmaps")
