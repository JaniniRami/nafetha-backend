from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import HTTPException
from passlib.context import CryptContext

from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Used when login email is unknown so verify still runs (timing / enumeration).
_DUMMY_BCRYPT_HASH = (
    "$2b$12$4KvzJYXPMOgq1xyBKDd9hu.w.PZtjKQPTX.y.xtJTXHYQCCSklqZu"
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def verify_password_or_dummy(plain_password: str, stored_hash: str | None) -> bool:
    """Like verify_password, but uses a dummy hash when ``stored_hash`` is None (unknown user)."""
    h = stored_hash if stored_hash is not None else _DUMMY_BCRYPT_HASH
    return verify_password(plain_password, h)


def _require_jwt_secret() -> None:
    if not JWT_SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set — add a long random secret to your environment "
            "(e.g. openssl rand -hex 32)"
        )


def _encode_token(payload: dict) -> str:
    _require_jwt_secret()
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_access_token(user_id: UUID, email: str) -> tuple[str, int]:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expires_in = int(timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES).total_seconds())
    token = _encode_token(
        {
            "sub": str(user_id),
            "email": email,
            "type": "access",
            "exp": expire,
        }
    )
    return token, expires_in


def create_refresh_token(user_id: UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return _encode_token(
        {
            "sub": str(user_id),
            "type": "refresh",
            "exp": expire,
        }
    )


def decode_token(token: str) -> dict:
    _require_jwt_secret()
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def decode_access_token(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


def decode_refresh_token(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload
