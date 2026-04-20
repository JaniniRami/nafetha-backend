"""add displayed fields to companies

Revision ID: 20260420_0014
Revises: 20260416_0013
Create Date: 2026-04-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260420_0014"
down_revision: Union[str, None] = "20260416_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("displayed_description", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("displayed_keywords", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "displayed_keywords")
    op.drop_column("companies", "displayed_description")
