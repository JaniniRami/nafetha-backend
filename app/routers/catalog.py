"""Authenticated read-only access to scraped jobs and companies."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import ScrapedCompany, ScrapedJob, User
from app.schemas import ScrapedCompanyOut, ScrapedJobOut

router = APIRouter(tags=["catalog"])


@router.get("/jobs", response_model=list[ScrapedJobOut])
def list_jobs(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ScrapedJob]:
    stmt = select(ScrapedJob).order_by(ScrapedJob.scraped_at.desc())
    return list(db.scalars(stmt).all())


@router.get("/companies", response_model=list[ScrapedCompanyOut])
def list_companies(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ScrapedCompany]:
    stmt = (
        select(ScrapedCompany)
        .where(ScrapedCompany.blacklisted.is_(False))
        .order_by(ScrapedCompany.scraped_at.desc())
    )
    return list(db.scalars(stmt).all())
