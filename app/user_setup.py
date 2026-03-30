"""Helpers for user-facing setup flags (onboarding, interests, etc.)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ProfileInterest, User, UserProfile
from app.schemas import TokenUserOut, UserSetupStatus


def user_has_saved_interests(db: Session, user: User) -> bool:
    profile_id = db.scalar(select(UserProfile.id).where(UserProfile.user_id == user.id))
    if profile_id is None:
        return False
    n = db.scalar(
        select(func.count())
        .select_from(ProfileInterest)
        .where(ProfileInterest.user_profile_id == profile_id)
    )
    return bool(n)


def build_token_user_out(db: Session, user: User) -> TokenUserOut:
    return TokenUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        setup=UserSetupStatus(
            onboarded=user.onboarded,
            interests_set=user_has_saved_interests(db, user),
        ),
    )
