from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import DEFAULT_USER_ROLE, User, UserProfile
from app.schemas import AuthSession, RefreshTokenIn, TokenUserOut, UserLogin, UserRegister
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


def _auth_session_for_user(user: User, db: Session) -> AuthSession:
    access_token, expires_in = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)
    return AuthSession(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=build_token_user_out(db, user),
    )


def _set_session_if_requested(request: Request, user: User, use_session_cookie: bool) -> None:
    if use_session_cookie:
        request.session["user_id"] = str(user.id)


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
