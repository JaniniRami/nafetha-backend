"""add skill column to profile_prerequisites

Revision ID: 20260423_0027
Revises: 20260423_0026
Create Date: 2026-04-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260423_0027"
down_revision: Union[str, None] = "20260423_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = inspector.get_columns(table_name)
    return any(c.get("name") == column_name for c in cols)


def _has_unique_constraint(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    uniques = inspector.get_unique_constraints(table_name)
    return any(u.get("name") == constraint_name for u in uniques)


def upgrade() -> None:
    if not _has_table("profile_prerequisites"):
        return

    if not _has_column("profile_prerequisites", "skill"):
        op.add_column(
            "profile_prerequisites",
            sa.Column("skill", sa.String(length=255), nullable=False, server_default=""),
        )
        op.alter_column("profile_prerequisites", "skill", server_default=None)

    if _has_unique_constraint("profile_prerequisites", "uq_profile_prerequisites_profile_prerequisite"):
        op.drop_constraint(
            "uq_profile_prerequisites_profile_prerequisite",
            "profile_prerequisites",
            type_="unique",
        )
    op.create_unique_constraint(
        "uq_profile_prerequisites_profile_prerequisite",
        "profile_prerequisites",
        ["user_profile_id", "skill", "prerequisite"],
    )


def downgrade() -> None:
    if not _has_table("profile_prerequisites"):
        return

    if _has_unique_constraint("profile_prerequisites", "uq_profile_prerequisites_profile_prerequisite"):
        op.drop_constraint(
            "uq_profile_prerequisites_profile_prerequisite",
            "profile_prerequisites",
            type_="unique",
        )
    op.create_unique_constraint(
        "uq_profile_prerequisites_profile_prerequisite",
        "profile_prerequisites",
        ["user_profile_id", "prerequisite"],
    )

    if _has_column("profile_prerequisites", "skill"):
        op.drop_column("profile_prerequisites", "skill")
