"""add displayed_description and displayed_keywords to jobs

Revision ID: 20260421_0018
Revises: 20260421_0017
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260421_0018"
down_revision: Union[str, None] = "20260421_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("displayed_description", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("displayed_keywords", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "displayed_keywords")
    op.drop_column("jobs", "displayed_description")
