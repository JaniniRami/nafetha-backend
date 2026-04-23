"""add keywords column to volunteering events

Revision ID: 20260422_0022
Revises: 20260422_0021
Create Date: 2026-04-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260422_0022"
down_revision: Union[str, None] = "20260422_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def upgrade() -> None:
    if not _has_column("volunteering_events", "keywords"):
        op.add_column("volunteering_events", sa.Column("keywords", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    if _has_column("volunteering_events", "keywords"):
        op.drop_column("volunteering_events", "keywords")
