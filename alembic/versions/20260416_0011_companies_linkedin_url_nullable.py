"""companies.linkedin_url nullable

Revision ID: 20260416_0011
Revises: 20260331_0010
Create Date: 2026-04-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260416_0011"
down_revision: Union[str, None] = "20260331_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "companies",
        "linkedin_url",
        existing_type=sa.String(length=1024),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "companies",
        "linkedin_url",
        existing_type=sa.String(length=1024),
        nullable=False,
    )
