"""add companies.blacklisted

Revision ID: 20260323_0007
Revises: 20260323_0006
Create Date: 2026-03-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260323_0007"
down_revision: Union[str, None] = "20260323_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "blacklisted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("companies", "blacklisted")
