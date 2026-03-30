"""users and user_profiles primary keys to UUID

Revision ID: 20260331_0009
Revises: 20260331_0008
Create Date: 2026-03-31

Destroys existing user_profiles rows. Existing users get new UUID ids (JWTs / old
integer ids are invalidated). Use only when local data loss is acceptable.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260331_0009"
down_revision: Union[str, None] = "20260331_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("user_profiles")

    op.drop_constraint("users_pkey", "users", type_="primary")
    op.drop_column("users", "id")

    op.add_column(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.create_primary_key("pk_users", "users", ["id"])

    op.create_table(
        "user_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
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

    op.drop_constraint("pk_users", "users", type_="primary")
    op.drop_column("users", "id")

    op.add_column(
        "users",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
    )
    op.create_primary_key("pk_users", "users", ["id"])

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
