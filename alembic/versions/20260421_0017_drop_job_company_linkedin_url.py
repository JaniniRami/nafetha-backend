"""drop company_linkedin_url from jobs

Revision ID: 20260421_0017
Revises: 20260421_0016
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260421_0017"
down_revision: Union[str, None] = "20260421_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("jobs", "company_linkedin_url")


def downgrade() -> None:
    op.add_column("jobs", sa.Column("company_linkedin_url", sa.String(length=1024), nullable=True))
