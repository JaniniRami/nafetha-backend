"""create companies and link jobs

Revision ID: 20260323_0005
Revises: 20260323_0004
Create Date: 2026-03-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260323_0005"
down_revision: Union[str, None] = "20260323_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_name", sa.String(length=512), nullable=False),
        sa.Column("linkedin_url", sa.String(length=1024), nullable=False),
        sa.Column("industry", sa.String(length=255), nullable=True),
        sa.Column("company_size", sa.String(length=255), nullable=True),
        sa.Column("website", sa.String(length=1024), nullable=True),
        sa.Column("phone", sa.String(length=255), nullable=True),
        sa.Column("about_us", sa.Text(), nullable=True),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_companies_company_name"), "companies", ["company_name"], unique=True)
    op.create_index(op.f("ix_companies_linkedin_url"), "companies", ["linkedin_url"], unique=True)

    op.add_column("jobs", sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_jobs_company_id"), "jobs", ["company_id"], unique=False)
    op.create_foreign_key(
        "fk_jobs_company_id_companies",
        "jobs",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_jobs_company_id_companies", "jobs", type_="foreignkey")
    op.drop_index(op.f("ix_jobs_company_id"), table_name="jobs")
    op.drop_column("jobs", "company_id")

    op.drop_index(op.f("ix_companies_linkedin_url"), table_name="companies")
    op.drop_index(op.f("ix_companies_company_name"), table_name="companies")
    op.drop_table("companies")
