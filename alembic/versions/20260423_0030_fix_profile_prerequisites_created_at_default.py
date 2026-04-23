"""restore created_at default on profile_prerequisites

Revision ID: 20260423_0030
Revises: 20260423_0029
Create Date: 2026-04-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260423_0030"
down_revision: Union[str, None] = "20260423_0029"
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


def upgrade() -> None:
    if not _has_table("profile_prerequisites"):
        return
    if not _has_column("profile_prerequisites", "created_at"):
        return

    op.alter_column(
        "profile_prerequisites",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def downgrade() -> None:
    if not _has_table("profile_prerequisites"):
        return
    if not _has_column("profile_prerequisites", "created_at"):
        return

    op.alter_column(
        "profile_prerequisites",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=None,
    )
