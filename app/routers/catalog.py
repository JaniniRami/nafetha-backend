"""Authenticated read-only access to scraped jobs and companies."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import CommunityEvent, ScrapedCompany, ScrapedJob, User, UserCatalogMatchScore, VolunteeringEvent
from app.profile_matching import get_persisted_catalog_match_scores_for_user
from app.schemas import (
    CatalogItemMatchScoreOut,
    CatalogMatchScoresOut,
    CommunityEventOut,
    DailyHighlightsOut,
    DailyHighlightUserOut,
    ScrapedCompanyOut,
    ScrapedJobOut,
    VolunteeringEventOut,
)

router = APIRouter(tags=["catalog"])
_VALID_CATALOG_TYPES = {
    "jobs",
    "companies",
    "communities",
    "community_events",
    "volunteering_events",
}


def _matching_percent_map(
    db: Session,
    user_id: UUID,
    catalog_type: str,
) -> dict[UUID, float]:
    rows = list(
        db.execute(
            select(UserCatalogMatchScore.item_id, UserCatalogMatchScore.score_percent).where(
                UserCatalogMatchScore.user_id == user_id,
                UserCatalogMatchScore.catalog_type == catalog_type,
            )
        ).all()
    )
    return {item_id: float(score_percent) for item_id, score_percent in rows}


def _top_match_for_type(
    db: Session,
    user_id: UUID,
    catalog_type: str,
) -> tuple[UUID, float] | None:
    row = db.execute(
        select(UserCatalogMatchScore.item_id, UserCatalogMatchScore.score_percent)
        .where(
            UserCatalogMatchScore.user_id == user_id,
            UserCatalogMatchScore.catalog_type == catalog_type,
        )
        .order_by(UserCatalogMatchScore.score_percent.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    item_id, score_percent = row
    return item_id, float(score_percent)


def _top_environmental_volunteering_match(
    db: Session,
    user_id: UUID,
) -> tuple[UUID, float] | None:
    row = db.execute(
        select(UserCatalogMatchScore.item_id, UserCatalogMatchScore.score_percent)
        .join(VolunteeringEvent, VolunteeringEvent.id == UserCatalogMatchScore.item_id)
        .where(
            UserCatalogMatchScore.user_id == user_id,
            UserCatalogMatchScore.catalog_type == "volunteering_events",
            func.lower(func.trim(VolunteeringEvent.keywords)).in_(("enviromental", "environmental")),
        )
        .order_by(UserCatalogMatchScore.score_percent.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    item_id, score_percent = row
    return item_id, float(score_percent)


@router.get("/jobs", response_model=list[ScrapedJobOut])
def list_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ScrapedJobOut]:
    stmt = (
        select(ScrapedJob)
        .options(selectinload(ScrapedJob.company))
        .order_by(ScrapedJob.scraped_at.desc())
    )
    rows = list(db.scalars(stmt).all())
    scores = _matching_percent_map(db, current_user.id, "jobs")
    out: list[ScrapedJobOut] = []
    for row in rows:
        payload = ScrapedJobOut.model_validate(row).model_dump()
        payload["matching_percentage"] = scores.get(row.id)
        out.append(ScrapedJobOut.model_validate(payload))
    out.sort(
        key=lambda item: (
            item.matching_percentage is None,
            -(item.matching_percentage or 0.0),
        )
    )
    return out


@router.get("/match-scores", response_model=CatalogMatchScoresOut)
def get_profile_match_scores(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CatalogMatchScoresOut:
    try:
        raw = get_persisted_catalog_match_scores_for_user(db, current_user)
        if raw is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Match scores are not generated yet for this user",
            )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Catalog embedding cache is missing on the server",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute match scores: {exc}",
        ) from exc

    return CatalogMatchScoresOut.model_validate(raw)


@router.get("/match-score/{item_id}", response_model=CatalogItemMatchScoreOut)
def get_item_match_score(
    item_id: UUID,
    catalog_type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CatalogItemMatchScoreOut:
    catalog_type_clean = (catalog_type or "").strip().lower()
    if catalog_type_clean not in _VALID_CATALOG_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "catalog_type must be one of: "
                "jobs, companies, communities, community_events, volunteering_events"
            ),
        )

    score = db.scalar(
        select(UserCatalogMatchScore.score_percent).where(
            UserCatalogMatchScore.user_id == current_user.id,
            UserCatalogMatchScore.catalog_type == catalog_type_clean,
            UserCatalogMatchScore.item_id == item_id,
        )
    )
    if score is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Matching score not found for this item id and catalog type",
        )

    return CatalogItemMatchScoreOut(
        id=item_id,
        catalog_type=catalog_type_clean,
        matching_percentage=float(score),
    )


@router.get("/daily-highlights", response_model=DailyHighlightsOut)
def get_daily_highlights(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyHighlightsOut:
    top_job = _top_match_for_type(db, current_user.id, "jobs")
    top_volunteering_event = _top_environmental_volunteering_match(db, current_user.id)
    top_community_event = _top_match_for_type(db, current_user.id, "community_events")

    job = None
    job_score = None
    if top_job is not None:
        job_id, job_score = top_job
        job = db.scalar(
            select(ScrapedJob)
            .options(selectinload(ScrapedJob.company))
            .where(ScrapedJob.id == job_id)
        )

    volunteering_event = None
    volunteering_score = None
    if top_volunteering_event is not None:
        event_id, volunteering_score = top_volunteering_event
        volunteering_event = db.get(VolunteeringEvent, event_id)

    community_event = None
    community_score = None
    if top_community_event is not None:
        event_id, community_score = top_community_event
        community_event = db.get(CommunityEvent, event_id)

    job_out = None
    if job is not None:
        job_payload = ScrapedJobOut.model_validate(job).model_dump()
        job_payload["matching_percentage"] = job_score
        job_out = ScrapedJobOut.model_validate(job_payload)

    volunteering_out = None
    if volunteering_event is not None:
        volunteering_payload = VolunteeringEventOut.model_validate(volunteering_event).model_dump()
        volunteering_payload["matching_percentage"] = volunteering_score
        volunteering_out = VolunteeringEventOut.model_validate(volunteering_payload)

    community_out = None
    if community_event is not None:
        community_payload = CommunityEventOut.model_validate(community_event).model_dump()
        community_payload["matching_percentage"] = community_score
        community_out = CommunityEventOut.model_validate(community_payload)

    return DailyHighlightsOut(
        user=DailyHighlightUserOut.model_validate(current_user),
        job=job_out,
        volunteering_event=volunteering_out,
        community_event=community_out,
    )


@router.get("/companies", response_model=list[ScrapedCompanyOut])
def list_companies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ScrapedCompanyOut]:
    stmt = (
        select(ScrapedCompany)
        .where(ScrapedCompany.blacklisted.is_(False))
        .order_by(ScrapedCompany.scraped_at.desc())
    )
    rows = list(db.scalars(stmt).all())
    scores = _matching_percent_map(db, current_user.id, "companies")
    out: list[ScrapedCompanyOut] = []
    for row in rows:
        payload = ScrapedCompanyOut.model_validate(row).model_dump()
        payload["matching_percentage"] = scores.get(row.id)
        out.append(ScrapedCompanyOut.model_validate(payload))
    out.sort(
        key=lambda item: (
            item.matching_percentage is None,
            -(item.matching_percentage or 0.0),
        )
    )
    return out


@router.get("/companies/{company_id}", response_model=ScrapedCompanyOut)
def get_company(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScrapedCompanyOut:
    row = db.get(ScrapedCompany, company_id)
    if row is None or row.blacklisted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    score = db.scalar(
        select(UserCatalogMatchScore.score_percent).where(
            UserCatalogMatchScore.user_id == current_user.id,
            UserCatalogMatchScore.catalog_type == "companies",
            UserCatalogMatchScore.item_id == company_id,
        )
    )
    payload = ScrapedCompanyOut.model_validate(row).model_dump()
    payload["matching_percentage"] = float(score) if isinstance(score, Decimal) else (float(score) if score is not None else None)
    return ScrapedCompanyOut.model_validate(payload)


@router.get("/volunteering-events", response_model=list[VolunteeringEventOut])
def list_volunteering_events(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[VolunteeringEvent]:
    stmt = select(VolunteeringEvent).order_by(VolunteeringEvent.scraped_at.desc())
    return list(db.scalars(stmt).all())


@router.get("/volunteering-events/{event_id}", response_model=VolunteeringEventOut)
def get_volunteering_event(
    event_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VolunteeringEvent:
    row = db.get(VolunteeringEvent, event_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Volunteering event not found")
    return row
