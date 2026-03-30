"""add user.role default student

Revision ID: 20250322_0002
Revises: 20250322_0001
Create Date: 2025-03-22

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20250322_0002"
down_revision: Union[str, None] = "20250322_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=50),
            server_default=sa.text("'student'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
