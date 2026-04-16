"""Communities, community events, subscriptions, and event favorites (authenticated)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import (
    Community,
    CommunityEvent,
    User,
    UserCommunityEventFavorite,
    UserCommunitySubscription,
)
from app.schemas import (
    CommunityCreate,
    CommunityEventCreate,
    CommunityEventOut,
    CommunityEventUpdate,
    CommunityOut,
    CommunityUpdate,
    FavoriteStateOut,
    SubscriptionStateOut,
)

router = APIRouter(prefix="/communities", tags=["communities"])


def _can_manage_community(user: User, community: Community) -> bool:
    if user.role == "superadmin":
        return True
    if community.created_by_user_id is None:
        return False
    return community.created_by_user_id == user.id


def _get_community_or_404(db: Session, community_id: UUID) -> Community:
    row = db.get(Community, community_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found")
    return row


def _get_event_in_community_or_404(db: Session, community_id: UUID, event_id: UUID) -> CommunityEvent:
    event = db.get(CommunityEvent, event_id)
    if event is None or event.community_id != community_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@router.get("", response_model=list[CommunityOut])
def list_communities(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Community]:
    stmt = select(Community).order_by(Community.created_at.desc())
    return list(db.scalars(stmt).all())


@router.post("", response_model=CommunityOut, status_code=status.HTTP_201_CREATED)
def create_community(
    payload: CommunityCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Community:
    row = Community(
        name=payload.name,
        description=payload.description,
        website=payload.website,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/me/subscriptions", response_model=list[CommunityOut])
def list_my_subscribed_communities(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Community]:
    stmt = (
        select(Community)
        .join(UserCommunitySubscription, UserCommunitySubscription.community_id == Community.id)
        .where(UserCommunitySubscription.user_id == current_user.id)
        .order_by(UserCommunitySubscription.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.get("/me/favorite-events", response_model=list[CommunityEventOut])
def list_my_favorite_events(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CommunityEvent]:
    stmt = (
        select(CommunityEvent)
        .join(UserCommunityEventFavorite, UserCommunityEventFavorite.event_id == CommunityEvent.id)
        .where(UserCommunityEventFavorite.user_id == current_user.id)
        .order_by(CommunityEvent.event_at.asc())
    )
    return list(db.scalars(stmt).all())


@router.get("/{community_id}", response_model=CommunityOut)
def get_community(
    community_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Community:
    return _get_community_or_404(db, community_id)


@router.patch("/{community_id}", response_model=CommunityOut)
def update_community(
    community_id: UUID,
    payload: CommunityUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Community:
    community = _get_community_or_404(db, community_id)
    if not _can_manage_community(current_user, community):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to edit this community")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    if "name" in data:
        community.name = data["name"]
    if "description" in data:
        community.description = data["description"]
    if "website" in data:
        community.website = data["website"]

    db.commit()
    db.refresh(community)
    return community


@router.delete("/{community_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_community(
    community_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    community = _get_community_or_404(db, community_id)
    if not _can_manage_community(current_user, community):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to delete this community")
    db.delete(community)
    db.commit()


@router.get("/{community_id}/events", response_model=list[CommunityEventOut])
def list_community_events(
    community_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CommunityEvent]:
    _get_community_or_404(db, community_id)
    stmt = (
        select(CommunityEvent)
        .where(CommunityEvent.community_id == community_id)
        .order_by(CommunityEvent.event_at.asc())
    )
    return list(db.scalars(stmt).all())


@router.post(
    "/{community_id}/events",
    response_model=CommunityEventOut,
    status_code=status.HTTP_201_CREATED,
)
def create_community_event(
    community_id: UUID,
    payload: CommunityEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommunityEvent:
    community = _get_community_or_404(db, community_id)
    if not _can_manage_community(current_user, community):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to add events to this community")

    row = CommunityEvent(
        community_id=community_id,
        name=payload.name,
        event_at=payload.event_at,
        location=payload.location,
        description=payload.description,
        website=payload.website,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{community_id}/events/{event_id}", response_model=CommunityEventOut)
def get_community_event(
    community_id: UUID,
    event_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommunityEvent:
    return _get_event_in_community_or_404(db, community_id, event_id)


@router.patch("/{community_id}/events/{event_id}", response_model=CommunityEventOut)
def update_community_event(
    community_id: UUID,
    event_id: UUID,
    payload: CommunityEventUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommunityEvent:
    community = _get_community_or_404(db, community_id)
    if not _can_manage_community(current_user, community):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to edit events for this community")

    event = _get_event_in_community_or_404(db, community_id, event_id)

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    if "name" in data:
        event.name = data["name"]
    if "event_at" in data:
        event.event_at = data["event_at"]
    if "location" in data:
        event.location = data["location"]
    if "description" in data:
        event.description = data["description"]
    if "website" in data:
        event.website = data["website"]

    db.commit()
    db.refresh(event)
    return event


@router.delete("/{community_id}/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_community_event(
    community_id: UUID,
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    community = _get_community_or_404(db, community_id)
    if not _can_manage_community(current_user, community):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to delete events for this community")

    event = _get_event_in_community_or_404(db, community_id, event_id)
    db.delete(event)
    db.commit()


@router.post("/{community_id}/subscribe", response_model=SubscriptionStateOut)
def subscribe_to_community(
    community_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubscriptionStateOut:
    _get_community_or_404(db, community_id)
    existing = db.scalar(
        select(UserCommunitySubscription).where(
            UserCommunitySubscription.user_id == current_user.id,
            UserCommunitySubscription.community_id == community_id,
        )
    )
    if existing is not None:
        return SubscriptionStateOut(community_id=community_id, subscribed=True)

    row = UserCommunitySubscription(user_id=current_user.id, community_id=community_id)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return SubscriptionStateOut(community_id=community_id, subscribed=True)
    return SubscriptionStateOut(community_id=community_id, subscribed=True)


@router.delete("/{community_id}/subscribe", response_model=SubscriptionStateOut)
def unsubscribe_from_community(
    community_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubscriptionStateOut:
    _get_community_or_404(db, community_id)
    sub = db.scalar(
        select(UserCommunitySubscription).where(
            UserCommunitySubscription.user_id == current_user.id,
            UserCommunitySubscription.community_id == community_id,
        )
    )
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not subscribed to this community")
    db.delete(sub)
    db.commit()
    return SubscriptionStateOut(community_id=community_id, subscribed=False)


@router.post(
    "/{community_id}/events/{event_id}/favorite",
    response_model=FavoriteStateOut,
)
def favorite_community_event(
    community_id: UUID,
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FavoriteStateOut:
    _get_event_in_community_or_404(db, community_id, event_id)
    existing = db.scalar(
        select(UserCommunityEventFavorite).where(
            UserCommunityEventFavorite.user_id == current_user.id,
            UserCommunityEventFavorite.event_id == event_id,
        )
    )
    if existing is not None:
        return FavoriteStateOut(event_id=event_id, favorited=True)

    row = UserCommunityEventFavorite(user_id=current_user.id, event_id=event_id)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return FavoriteStateOut(event_id=event_id, favorited=True)
    return FavoriteStateOut(event_id=event_id, favorited=True)


@router.delete(
    "/{community_id}/events/{event_id}/favorite",
    response_model=FavoriteStateOut,
)
def unfavorite_community_event(
    community_id: UUID,
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FavoriteStateOut:
    _get_event_in_community_or_404(db, community_id, event_id)
    fav = db.scalar(
        select(UserCommunityEventFavorite).where(
            UserCommunityEventFavorite.user_id == current_user.id,
            UserCommunityEventFavorite.event_id == event_id,
        )
    )
    if fav is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event is not in your favorites")
    db.delete(fav)
    db.commit()
    return FavoriteStateOut(event_id=event_id, favorited=False)
