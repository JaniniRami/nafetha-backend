"""user favorites for catalog companies and jobs (internships)

Revision ID: 20260422_0019
Revises: 20260421_0018
Create Date: 2026-04-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260422_0019"
down_revision: Union[str, None] = "20260421_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_company_favorites",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "company_id", name="uq_user_company_favorite"),
    )
    op.create_index(op.f("ix_user_company_favorites_company_id"), "user_company_favorites", ["company_id"], unique=False)
    op.create_index(op.f("ix_user_company_favorites_user_id"), "user_company_favorites", ["user_id"], unique=False)

    op.create_table(
        "user_job_favorites",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "job_id", name="uq_user_job_favorite"),
    )
    op.create_index(op.f("ix_user_job_favorites_job_id"), "user_job_favorites", ["job_id"], unique=False)
    op.create_index(op.f("ix_user_job_favorites_user_id"), "user_job_favorites", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_job_favorites_user_id"), table_name="user_job_favorites")
    op.drop_index(op.f("ix_user_job_favorites_job_id"), table_name="user_job_favorites")
    op.drop_table("user_job_favorites")
    op.drop_index(op.f("ix_user_company_favorites_user_id"), table_name="user_company_favorites")
    op.drop_index(op.f("ix_user_company_favorites_company_id"), table_name="user_company_favorites")
    op.drop_table("user_company_favorites")
