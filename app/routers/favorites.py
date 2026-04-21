"""User favorites for catalog companies and scraped jobs (internships)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import (
    ScrapedCompany,
    ScrapedJob,
    User,
    UserCompanyFavorite,
    UserJobFavorite,
)
from app.schemas import (
    CompanyFavoriteStateOut,
    JobFavoriteStateOut,
    ScrapedCompanyOut,
    ScrapedJobOut,
)

router = APIRouter(prefix="/me/favorites", tags=["favorites"])


def _catalog_company_or_404(db: Session, company_id: UUID) -> ScrapedCompany:
    row = db.get(ScrapedCompany, company_id)
    if row is None or row.blacklisted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return row


def _job_row_or_404(db: Session, job_row_id: UUID) -> ScrapedJob:
    row = db.get(ScrapedJob, job_row_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return row


@router.get("/companies", response_model=list[ScrapedCompanyOut])
def list_favorite_companies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ScrapedCompany]:
    stmt = (
        select(ScrapedCompany)
        .join(UserCompanyFavorite, UserCompanyFavorite.company_id == ScrapedCompany.id)
        .where(UserCompanyFavorite.user_id == current_user.id)
        .where(ScrapedCompany.blacklisted.is_(False))
        .order_by(UserCompanyFavorite.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.get("/jobs", response_model=list[ScrapedJobOut])
def list_favorite_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ScrapedJob]:
    stmt = (
        select(ScrapedJob)
        .join(UserJobFavorite, UserJobFavorite.job_id == ScrapedJob.id)
        .where(UserJobFavorite.user_id == current_user.id)
        .options(selectinload(ScrapedJob.company))
        .order_by(UserJobFavorite.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.get("/companies/{company_id}", response_model=CompanyFavoriteStateOut)
def get_company_favorite_state(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyFavoriteStateOut:
    row = db.get(ScrapedCompany, company_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    fav = db.scalar(
        select(UserCompanyFavorite).where(
            UserCompanyFavorite.user_id == current_user.id,
            UserCompanyFavorite.company_id == company_id,
        )
    )
    if row.blacklisted and fav is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return CompanyFavoriteStateOut(company_id=company_id, favorited=fav is not None)


@router.get("/jobs/{job_row_id}", response_model=JobFavoriteStateOut)
def get_job_favorite_state(
    job_row_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobFavoriteStateOut:
    _job_row_or_404(db, job_row_id)
    fav = db.scalar(
        select(UserJobFavorite).where(
            UserJobFavorite.user_id == current_user.id,
            UserJobFavorite.job_id == job_row_id,
        )
    )
    return JobFavoriteStateOut(job_row_id=job_row_id, favorited=fav is not None)


@router.post("/companies/{company_id}", response_model=CompanyFavoriteStateOut)
def favorite_company(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyFavoriteStateOut:
    _catalog_company_or_404(db, company_id)
    existing = db.scalar(
        select(UserCompanyFavorite).where(
            UserCompanyFavorite.user_id == current_user.id,
            UserCompanyFavorite.company_id == company_id,
        )
    )
    if existing is not None:
        return CompanyFavoriteStateOut(company_id=company_id, favorited=True)

    row = UserCompanyFavorite(user_id=current_user.id, company_id=company_id)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return CompanyFavoriteStateOut(company_id=company_id, favorited=True)
    return CompanyFavoriteStateOut(company_id=company_id, favorited=True)


@router.delete("/companies/{company_id}", response_model=CompanyFavoriteStateOut)
def unfavorite_company(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyFavoriteStateOut:
    fav = db.scalar(
        select(UserCompanyFavorite).where(
            UserCompanyFavorite.user_id == current_user.id,
            UserCompanyFavorite.company_id == company_id,
        )
    )
    if fav is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company is not in your favorites",
        )
    db.delete(fav)
    db.commit()
    return CompanyFavoriteStateOut(company_id=company_id, favorited=False)


@router.post("/jobs/{job_row_id}", response_model=JobFavoriteStateOut)
def favorite_job(
    job_row_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobFavoriteStateOut:
    _job_row_or_404(db, job_row_id)
    existing = db.scalar(
        select(UserJobFavorite).where(
            UserJobFavorite.user_id == current_user.id,
            UserJobFavorite.job_id == job_row_id,
        )
    )
    if existing is not None:
        return JobFavoriteStateOut(job_row_id=job_row_id, favorited=True)

    row = UserJobFavorite(user_id=current_user.id, job_id=job_row_id)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return JobFavoriteStateOut(job_row_id=job_row_id, favorited=True)
    return JobFavoriteStateOut(job_row_id=job_row_id, favorited=True)


@router.delete("/jobs/{job_row_id}", response_model=JobFavoriteStateOut)
def unfavorite_job(
    job_row_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobFavoriteStateOut:
    _job_row_or_404(db, job_row_id)
    fav = db.scalar(
        select(UserJobFavorite).where(
            UserJobFavorite.user_id == current_user.id,
            UserJobFavorite.job_id == job_row_id,
        )
    )
    if fav is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job is not in your favorites",
        )
    db.delete(fav)
    db.commit()
    return JobFavoriteStateOut(job_row_id=job_row_id, favorited=False)
