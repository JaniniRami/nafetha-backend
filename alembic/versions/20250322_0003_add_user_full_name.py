"""add user.full_name

Revision ID: 20250322_0003
Revises: 20250322_0002
Create Date: 2025-03-22

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20250322_0003"
down_revision: Union[str, None] = "20250322_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "full_name",
            sa.String(length=255),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    op.alter_column("users", "full_name", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "full_name")
