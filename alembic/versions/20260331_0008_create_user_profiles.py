"""create user_profiles

Revision ID: 20260331_0008
Revises: 20260323_0007
Create Date: 2026-03-31

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260331_0008"
down_revision: Union[str, None] = "20260323_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("university", sa.String(length=255), nullable=False),
        sa.Column("major", sa.String(length=255), nullable=False),
        sa.Column("year_of_study", sa.Integer(), nullable=False),
        sa.Column("graduation_semester", sa.String(length=10), nullable=False),
        sa.Column("graduation_year", sa.Integer(), nullable=False),
        sa.Column("gpa_scale", sa.Integer(), nullable=False),
        sa.Column("gpa_value", sa.Numeric(6, 3), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_profiles_user_id"),
        sa.CheckConstraint(
            "gpa_scale IN (5, 100)",
            name="ck_user_profiles_gpa_scale_valid",
        ),
        sa.CheckConstraint(
            "gpa_value >= 0 AND gpa_value <= gpa_scale",
            name="ck_user_profiles_gpa_value_valid",
        ),
        sa.CheckConstraint(
            "graduation_semester IN ('First','Second','Summer')",
            name="ck_user_profiles_graduation_semester_valid",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_profiles")

