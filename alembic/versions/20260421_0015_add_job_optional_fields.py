"""add extra_details to jobs

Revision ID: 20260421_0015
Revises: 20260420_0014
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260421_0015"
down_revision: Union[str, None] = "20260420_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("extra_details", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "extra_details")
