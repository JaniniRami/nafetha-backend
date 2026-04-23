from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import (
    CommunityEvent,
    DEFAULT_USER_ROLE,
    ScrapedJob,
    User,
    UserCatalogMatchScore,
    UserProfile,
    VolunteeringEvent,
)
from app.profile_matching import get_or_create_persisted_catalog_match_scores_for_user
from app.schemas import (
    AuthSession,
    CommunityEventOut,
    DailyHighlightsOut,
    DailyHighlightUserOut,
    RefreshTokenIn,
    ScrapedJobOut,
    TokenUserOut,
    UserLogin,
    UserProfileOut,
    UserRegister,
    VolunteeringEventOut,
)
from app.user_setup import build_token_user_out
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password_or_dummy,
)

router = APIRouter()
DEMO_EXISTING_LOGIN_EMAILS = {"r.janini@gju.edu.jo"}


def _top_match_item_id(db: Session, user_id: UUID, catalog_type: str) -> UUID | None:
    row = db.scalar(
        select(UserCatalogMatchScore.item_id)
        .where(
            UserCatalogMatchScore.user_id == user_id,
            UserCatalogMatchScore.catalog_type == catalog_type,
        )
        .order_by(UserCatalogMatchScore.score_percent.desc())
        .limit(1)
    )
    return row


def _top_environmental_volunteering_item_id(db: Session, user_id: UUID) -> UUID | None:
    return db.scalar(
        select(UserCatalogMatchScore.item_id)
        .join(VolunteeringEvent, VolunteeringEvent.id == UserCatalogMatchScore.item_id)
        .where(
            UserCatalogMatchScore.user_id == user_id,
            UserCatalogMatchScore.catalog_type == "volunteering_events",
            func.lower(func.trim(VolunteeringEvent.keywords)).in_(("enviromental", "environmental")),
        )
        .order_by(UserCatalogMatchScore.score_percent.desc())
        .limit(1)
    )


def _build_daily_highlights_for_user(db: Session, user: User) -> DailyHighlightsOut:
    top_job_id = _top_match_item_id(db, user.id, "jobs")
    top_volunteering_event_id = _top_environmental_volunteering_item_id(db, user.id)
    top_community_event_id = _top_match_item_id(db, user.id, "community_events")

    job = None
    if top_job_id is not None:
        job = db.scalar(
            select(ScrapedJob)
            .options(selectinload(ScrapedJob.company))
            .where(ScrapedJob.id == top_job_id)
        )

    volunteering_event = db.get(VolunteeringEvent, top_volunteering_event_id) if top_volunteering_event_id else None
    community_event = db.get(CommunityEvent, top_community_event_id) if top_community_event_id else None

    return DailyHighlightsOut(
        user=DailyHighlightUserOut.model_validate(user),
        job=ScrapedJobOut.model_validate(job) if job else None,
        volunteering_event=VolunteeringEventOut.model_validate(volunteering_event) if volunteering_event else None,
        community_event=CommunityEventOut.model_validate(community_event) if community_event else None,
    )


def _auth_session_for_user(user: User, db: Session) -> AuthSession:
    access_token, expires_in = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    return AuthSession(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=build_token_user_out(db, user),
        profile=UserProfileOut.model_validate(profile) if profile else None,
        daily_highlights=_build_daily_highlights_for_user(db, user),
    )


def _set_session_if_requested(request: Request, user: User, use_session_cookie: bool) -> None:
    if use_session_cookie:
        request.session["user_id"] = str(user.id)


def _best_effort_seed_match_scores(db: Session, user: User) -> None:
    """On login, ensure persisted catalog scores exist when profile data is available."""
    try:
        get_or_create_persisted_catalog_match_scores_for_user(db, user)
        print(f"[profile-match] trigger=login_seed success user_id={user.id}", flush=True)
    except Exception as exc:
        print(
            f"[profile-match] trigger=login_seed failed user_id={user.id} error={exc}",
            flush=True,
        )


@router.post("/register", response_model=AuthSession)
def register(
    request: Request,
    payload: UserRegister,
    db: Session = Depends(get_db),
):
    if payload.password != payload.password_confirm:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    email = str(payload.email).lower().strip()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        # Demo-only behavior: if this specific account is re-registered,
        # treat it as a successful login and return a fresh session.
        # Also reset onboarding to false for demo replay.
        if email in DEMO_EXISTING_LOGIN_EMAILS:
            # Demo reset behavior: remove previous profile/interests so onboarding
            # and interests flows start from a clean state.
            existing_profile = db.scalar(select(UserProfile).where(UserProfile.user_id == existing.id))
            if existing_profile is not None:
                db.delete(existing_profile)
            db.execute(delete(UserCatalogMatchScore).where(UserCatalogMatchScore.user_id == existing.id))
            existing.onboarded = False
            db.commit()
            db.refresh(existing)
            _set_session_if_requested(request, existing, payload.use_session_cookie)
            return _auth_session_for_user(existing, db)
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=DEFAULT_USER_ROLE,
        onboarded=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _set_session_if_requested(request, user, payload.use_session_cookie)
    return _auth_session_for_user(user, db)


@router.post("/login", response_model=AuthSession)
def login(request: Request, payload: UserLogin, db: Session = Depends(get_db)):
    email = str(payload.email).lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    stored = user.password_hash if user else None
    if user is None or not verify_password_or_dummy(payload.password, stored):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    _set_session_if_requested(request, user, payload.use_session_cookie)
    _best_effort_seed_match_scores(db, user)
    return _auth_session_for_user(user, db)


@router.post("/logout")
def logout(request: Request):
    """Ends the cookie session. The client should also delete stored JWTs."""
    request.session.clear()
    return {"ok": True}


@router.post("/auth/refresh", response_model=AuthSession)
def refresh_session(body: RefreshTokenIn, db: Session = Depends(get_db)):
    payload = decode_refresh_token(body.refresh_token)
    user_id = UUID(payload["sub"])
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return _auth_session_for_user(user, db)


@router.get("/me", response_model=TokenUserOut)
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return build_token_user_out(db, current_user)
