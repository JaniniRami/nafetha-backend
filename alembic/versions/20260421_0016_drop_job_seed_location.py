"""drop seed_location from jobs

Revision ID: 20260421_0016
Revises: 20260421_0015
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260421_0016"
down_revision: Union[str, None] = "20260421_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("jobs", "seed_location")


def downgrade() -> None:
    op.add_column("jobs", sa.Column("seed_location", sa.String(length=255), nullable=True))
