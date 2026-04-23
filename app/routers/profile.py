"""Profile-related API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import ProfileInterest, User, UserProfile
from app.profile_matching import persist_catalog_match_scores_for_user
from app.schemas import InterestsOut, InterestsReplaceIn, OnboardingIn, UserProfileOut

router = APIRouter(tags=["profile"])


def _get_profile(db: Session, user: User) -> UserProfile | None:
    return db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))


def _require_profile(db: Session, user: User) -> UserProfile:
    profile = _get_profile(db, user)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. Complete onboarding first.",
        )
    return profile


def _best_effort_recompute_profile_match_scores(db: Session, user: User) -> None:
    """Compute scores automatically after onboarding/interests changes; never block request on failures."""
    try:
        persist_catalog_match_scores_for_user(db, user)
        print(f"[profile-match] trigger=profile_update success user_id={user.id}", flush=True)
    except Exception as exc:
        print(
            f"[profile-match] trigger=profile_update failed user_id={user.id} error={exc}",
            flush=True,
        )


@router.get(
    "/profile",
    response_model=UserProfileOut,
)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileOut:
    """Return onboarding / academic profile for the current user."""
    return _require_profile(db, current_user)


@router.post(
    "/profile/onboarding",
    response_model=UserProfileOut,
)
def save_onboarding(
    payload: OnboardingIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileOut:
    """Create/update a user's onboarding profile, and flip `users.onboarded=true`."""
    if current_user.onboarded:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already onboarded")

    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == current_user.id))

    if profile is None:
        profile = UserProfile(
            user_id=current_user.id,
            university=payload.university,
            major=payload.major,
            year_of_study=payload.year_of_study,
            graduation_semester=payload.graduation_semester,
            graduation_year=payload.graduation_year,
            gpa_scale=payload.gpa_scale,
            gpa_value=payload.gpa_value,
        )
        db.add(profile)
    else:
        # User is not onboarded yet, so allow updating the existing row.
        profile.university = payload.university
        profile.major = payload.major
        profile.year_of_study = payload.year_of_study
        profile.graduation_semester = payload.graduation_semester
        profile.graduation_year = payload.graduation_year
        profile.gpa_scale = payload.gpa_scale
        profile.gpa_value = payload.gpa_value

    current_user.onboarded = True
    db.commit()
    db.refresh(profile)
    return profile


@router.get(
    "/profile/interests",
    response_model=InterestsOut,
)
def get_interests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterestsOut:
    """Return saved interests so the client can skip the picker if already set."""
    profile = _get_profile(db, current_user)
    if profile is None:
        return InterestsOut(interests=[], has_interests=False)

    rows = db.scalars(
        select(ProfileInterest.interest)
        .where(ProfileInterest.user_profile_id == profile.id)
        .order_by(ProfileInterest.interest)
    ).all()
    interests = list(rows)
    return InterestsOut(interests=interests, has_interests=bool(interests))


@router.put(
    "/profile/interests",
    response_model=InterestsOut,
)
def replace_interests(
    payload: InterestsReplaceIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterestsOut:
    """Replace all interests for this profile (use an empty list to clear)."""
    profile = _require_profile(db, current_user)

    db.execute(delete(ProfileInterest).where(ProfileInterest.user_profile_id == profile.id))
    for label in payload.interests:
        db.add(ProfileInterest(user_profile_id=profile.id, interest=label))
    db.commit()
    _best_effort_recompute_profile_match_scores(db, current_user)

    interests = sorted(payload.interests)
    return InterestsOut(interests=interests, has_interests=bool(interests))

