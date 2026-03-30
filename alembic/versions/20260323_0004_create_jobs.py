"""create jobs table

Revision ID: 20260323_0004
Revises: 20250322_0003
Create Date: 2026-03-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260323_0004"
down_revision: Union[str, None] = "20250322_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("job_title", sa.String(length=512), nullable=True),
        sa.Column("company_linkedin_url", sa.String(length=1024), nullable=True),
        sa.Column("posted_date", sa.String(length=255), nullable=True),
        sa.Column("job_description", sa.Text(), nullable=True),
        sa.Column("linkedin_url", sa.String(length=1024), nullable=False),
        sa.Column("seed_location", sa.String(length=255), nullable=True),
        sa.Column("keyword", sa.String(length=255), nullable=True),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobs_job_id"), "jobs", ["job_id"], unique=True)
    op.create_index(op.f("ix_jobs_linkedin_url"), "jobs", ["linkedin_url"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_jobs_linkedin_url"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_job_id"), table_name="jobs")
    op.drop_table("jobs")
