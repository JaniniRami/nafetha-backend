"""create profile_interests

Revision ID: 20260331_0010
Revises: 20260331_0009
Create Date: 2026-03-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260331_0010"
down_revision: Union[str, None] = "20260331_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profile_interests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("interest", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_profile_id",
            "interest",
            name="uq_profile_interests_profile_interest",
        ),
    )
    op.create_index(
        op.f("ix_profile_interests_user_profile_id"),
        "profile_interests",
        ["user_profile_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_profile_interests_user_profile_id"), table_name="profile_interests")
    op.drop_table("profile_interests")
