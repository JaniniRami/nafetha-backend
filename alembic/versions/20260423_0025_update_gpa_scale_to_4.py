"""update gpa scale from 5 to 4

Revision ID: 20260423_0025
Revises: 20260422_0024
Create Date: 2026-04-23

"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260423_0025"
down_revision: Union[str, None] = "20260422_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_user_profiles_gpa_scale_valid", "user_profiles", type_="check")
    op.create_check_constraint(
        "ck_user_profiles_gpa_scale_valid",
        "user_profiles",
        "gpa_scale IN (4, 100)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_profiles_gpa_scale_valid", "user_profiles", type_="check")
    op.create_check_constraint(
        "ck_user_profiles_gpa_scale_valid",
        "user_profiles",
        "gpa_scale IN (5, 100)",
    )
